package com.shopping.agent.data.repository

import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.model.Product
import com.shopping.agent.data.remote.ApiClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class CompareDimension(
    val name: String,
    val values: Map<String, String>,
    val winner: String?,
)

data class CompareResult(
    val dimensions: List<CompareDimension>,
    val summary: String,
    val productIds: List<String>,
)

class CompareRepository(
    private val baseUrl: String = NetworkConfig.BASE_URL
) {
    suspend fun fetchProducts(): List<Product>? = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.get("/products", mapOf("size" to "100"))
            val data = response.optJSONObject("data") ?: return@withContext null
            val items = data.optJSONArray("items") ?: return@withContext null
            val products = mutableListOf<Product>()
            for (i in 0 until items.length()) {
                val obj = items.getJSONObject(i)
                products.add(Product(
                    productId = obj.optString("product_id", ""),
                    title = obj.optString("title", ""),
                    brand = obj.optString("brand").takeIf { obj.has("brand") && !obj.isNull("brand") },
                    category = obj.optString("category", ""),
                    price = obj.optDouble("price", 0.0),
                    rating = obj.optDouble("rating", 3.0).toFloat(),
                    ratingCount = obj.optInt("rating_count", 0),
                    imageUrl = NetworkConfig.resolveImageUrl(obj.optString("image_url").takeIf { obj.has("image_url") && !obj.isNull("image_url") }),
                    imageUrls = listOf(),
                    highlights = listOf(),
                    attributes = mapOf(),
                    source = obj.optString("source", ""),
                ))
            }
            products
        } catch (e: Exception) {
            null
        }
    }

    suspend fun compareProducts(productIds: List<String>): CompareResult? = withContext(Dispatchers.IO) {
        try {
            val body = JSONObject().apply {
                put("product_ids", JSONArray(productIds))
            }

            val response = ApiClient.post("/products/compare", body.toString())
            val data = response.optJSONObject("data") ?: return@withContext null
            val dimsArray = data.optJSONArray("dimensions") ?: JSONArray()
            val dimensions = mutableListOf<CompareDimension>()
            for (i in 0 until dimsArray.length()) {
                val d = dimsArray.getJSONObject(i)
                val valuesObj = d.optJSONObject("values") ?: JSONObject()
                val values = mutableMapOf<String, String>()
                for (key in valuesObj.keys()) {
                    values[key] = valuesObj.optString(key, "")
                }
                dimensions.add(CompareDimension(
                    name = d.optString("name", ""),
                    values = values,
                    winner = d.optString("winner").takeIf { d.has("winner") && !d.isNull("winner") },
                ))
            }
            CompareResult(
                dimensions = dimensions,
                summary = data.optString("summary", ""),
                productIds = productIds,
            )
        } catch (e: Exception) {
            null
        }
    }
}
