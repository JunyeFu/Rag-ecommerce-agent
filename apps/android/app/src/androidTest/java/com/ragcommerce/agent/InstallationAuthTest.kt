package com.ragcommerce.agent

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.ragcommerce.agent.data.InstallationCipher
import com.ragcommerce.agent.data.remote.CommerceApi
import com.ragcommerce.agent.data.remote.AgentEventStream
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.flow.toList
import okhttp3.OkHttpClient
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import retrofit2.Retrofit
import retrofit2.HttpException
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class InstallationAuthTest {
    @Test
    fun keystoreRestAndSseUseRevocableServerCredentials() = runBlocking {
        val base = "http://127.0.0.1:59279/"
        val client = OkHttpClient()
        val api = Retrofit.Builder().baseUrl(base).client(client).build().create(CommerceApi::class.java)
        val issued = api.install().use { JSONObject(it.string()) }
        val token = issued.getString("token")
        val encrypted = InstallationCipher.encrypt(token)
        assertFalse(encrypted.contains(token))
        val authorization = "Bearer ${InstallationCipher.decrypt(encrypted)}"
        val body = "{\"goal\":\"通勤耳机,预算800元\"}".toRequestBody("application/json".toMediaType())
        val thread = api.createThread(authorization, body).use { JSONObject(it.string()).getString("thread_id") }
        val payload = "{\"text\":\"通勤耳机,预算800元\",\"media_ids\":[]}".toRequestBody("application/json".toMediaType())
        val run = api.createTurn(authorization, UUID.randomUUID().toString(), thread, payload).use { JSONObject(it.string()).getString("run_id") }
        val frames = withTimeout(15000) { AgentEventStream(client).frames("${base}v1/agent-runs/$run/events", authorization, null).toList() }
        assertTrue(frames.any { it.contains("event: message") })
        assertTrue(frames.any { it.contains("event: completed") })
        api.deleteMyData(authorization, "delete-my-data").use { }
        try {
            api.threads(authorization).use { }
            fail("revoked credential was accepted")
        } catch (error: HttpException) {
            assertEquals(401, error.code())
        }
    }
    @Test
    fun credentialUpgradePreservesOfflineNotesAndDropsStaleServerPointers() = runBlocking {
        val context = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext
        val database = androidx.room.Room.inMemoryDatabaseBuilder(context, com.ragcommerce.agent.data.local.ShoppingDatabase::class.java).build()
        val scope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.IO)
        val settings = androidx.datastore.preferences.core.PreferenceDataStoreFactory.create(scope = scope, produceFile = {
            java.io.File(context.cacheDir, "auth-${UUID.randomUUID()}.preferences_pb")
        })
        val legacy = com.ragcommerce.agent.data.local.MissionEntity("offline-note", "legacy offline note", 1L)
        database.shoppingDao().saveMission(legacy)
        settings.edit {
            it[stringPreferencesKey("install_user_id")] = "old-untrusted-uuid"
            it[stringPreferencesKey("active_thread_id")] = "stale-thread"
            it[stringPreferencesKey("legacy_marker")] = "keep"
        }
        val client = OkHttpClient()
        val api = Retrofit.Builder().baseUrl("http://127.0.0.1:59279/").client(client).build().create(CommerceApi::class.java)
        fun repository() = com.ragcommerce.agent.data.NetworkShoppingRepository(context, database.shoppingDao(), settings, api, AgentEventStream(client))
        try {
            assertNull(repository().restoreThread())
            val first = settings.data.first()
            assertEquals("keep", first[stringPreferencesKey("legacy_marker")])
            assertEquals(legacy, database.shoppingDao().observeMission().first())
            assertNull(first[stringPreferencesKey("active_thread_id")])
            assertNotEquals("old-untrusted-uuid", first[stringPreferencesKey("install_user_id")])
            repository().history()
            assertEquals(first[stringPreferencesKey("install_user_id")], settings.data.first()[stringPreferencesKey("install_user_id")])
            val encrypted = requireNotNull(first[stringPreferencesKey("installation_credential_encrypted_v1")])
            api.deleteMyData("Bearer ${InstallationCipher.decrypt(encrypted)}", "delete-my-data").use { }
        } finally {
            scope.cancel()
            database.close()
        }
    }

}
