package com.shopping.agent.data.remote

import com.shopping.agent.ShoppingApp
import com.shopping.agent.data.local.AuthManager
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val context = ShoppingApp.instance
        var token = AuthManager.ensureToken(context)

        val request = if (token.isNotBlank()) {
            chain.request().newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            chain.request()
        }

        val response = chain.proceed(request)

        if (response.code == 401) {
            response.close()
            AuthManager.clearToken(context)
            token = AuthManager.ensureToken(context)
            if (token.isNotBlank()) {
                val retryRequest = chain.request().newBuilder()
                    .header("Authorization", "Bearer $token")
                    .build()
                return chain.proceed(retryRequest)
            }
        }

        return response
    }
}
