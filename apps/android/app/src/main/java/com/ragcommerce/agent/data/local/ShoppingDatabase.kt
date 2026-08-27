package com.ragcommerce.agent.data.local

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "missions")
data class MissionEntity(
    @PrimaryKey val id: String,
    val goal: String,
    val updatedAtEpochMillis: Long,
)

@Entity(tableName = "saved_items")
data class SavedItemEntity(
    @PrimaryKey val itemKey: String,
    val kind: String,
    val externalId: String,
    val title: String,
    val sourceRef: String,
    val quantity: Int,
)

@Dao
interface ShoppingDao {
    @Query("SELECT * FROM missions ORDER BY updatedAtEpochMillis DESC LIMIT 1")
    fun observeMission(): Flow<MissionEntity?>

    @Query("SELECT * FROM saved_items ORDER BY itemKey")
    fun observeItems(): Flow<List<SavedItemEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveMission(value: MissionEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveItem(value: SavedItemEntity)

    @Query("DELETE FROM saved_items WHERE itemKey = :key")
    suspend fun deleteItem(key: String)
}

@Database(
    entities = [MissionEntity::class, SavedItemEntity::class],
    version = 1,
    exportSchema = true,
)
abstract class ShoppingDatabase : RoomDatabase() {
    abstract fun shoppingDao(): ShoppingDao
}
