package com.shopping.agent

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.memory.MemoryCache
import com.shopping.agent.data.local.AuthManager

/**
 * Application 入口 — 全局初始化
 */
class ShoppingApp : Application(), ImageLoaderFactory {

    override fun onCreate() {
        super.onCreate()
        instance = this
        kotlin.concurrent.thread {
            AuthManager.ensureToken(this)
        }
    }

    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .memoryCache {
            MemoryCache.Builder(this)
                .maxSizePercent(0.10)
                .build()
        }
        .diskCache {
            DiskCache.Builder()
                .directory(cacheDir.resolve("coil_cache"))
                .maxSizeBytes(50 * 1024 * 1024)
                .build()
        }
        .crossfade(300)
        .build()

    companion object {
        lateinit var instance: ShoppingApp
            private set
    }
}
