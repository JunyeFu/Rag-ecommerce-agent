package com.ragcommerce.agent.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import androidx.room.Room
import com.ragcommerce.agent.BuildConfig
import com.ragcommerce.agent.data.NetworkShoppingRepository
import com.ragcommerce.agent.data.ShoppingRepository
import com.ragcommerce.agent.data.local.ShoppingDao
import com.ragcommerce.agent.data.local.ShoppingDatabase
import com.ragcommerce.agent.data.remote.AgentEventStream
import com.ragcommerce.agent.data.remote.CommerceApi
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

private val Context.settingsDataStore by preferencesDataStore(name = "shopping_settings")

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    abstract fun bindShoppingRepository(value: NetworkShoppingRepository): ShoppingRepository
}

@Module
@InstallIn(SingletonComponent::class)
object AppModule {
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): ShoppingDatabase =
        Room.databaseBuilder(context, ShoppingDatabase::class.java, "shopping-v1.db").build()

    @Provides
    fun provideShoppingDao(database: ShoppingDatabase): ShoppingDao = database.shoppingDao()

    @Provides
    @Singleton
    fun provideSettings(@ApplicationContext context: Context): DataStore<Preferences> =
        context.settingsDataStore

    @Provides
    @Singleton
    fun provideHttpClient(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(client)
        .build()

    @Provides
    @Singleton
    fun provideApi(retrofit: Retrofit): CommerceApi = retrofit.create(CommerceApi::class.java)

    @Provides
    @Singleton
    fun provideEventStream(client: OkHttpClient): AgentEventStream = AgentEventStream(client)
}
