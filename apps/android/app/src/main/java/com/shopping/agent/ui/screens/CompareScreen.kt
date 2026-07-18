package com.shopping.agent.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import java.io.File
import java.text.SimpleDateFormat
import java.util.Locale
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import coil.compose.AsyncImage
import com.shopping.agent.data.mock.MockCompareData
import com.shopping.agent.data.model.Product
import com.shopping.agent.data.model.SSEEvent
import com.shopping.agent.data.remote.AudioClient
import com.shopping.agent.data.remote.SseClient
import com.shopping.agent.data.repository.CompareRepository
import com.shopping.agent.ui.components.*
import com.shopping.agent.ui.navigation.LocalOnMenuClick
import com.shopping.agent.ui.theme.*
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.launch

@Composable
fun CompareTabScreen() {
    var allProducts by remember { mutableStateOf(MockCompareData.products) }
    val categories = MockCompareData.categories
    var selectedCategory by remember { mutableStateOf(MockCompareData.defaultCategory) }
    var selectedProduct by remember { mutableStateOf<String?>(null) }

    // 本地搜索状态
    var searchQuery by remember { mutableStateOf("") }
    var searchResults by remember { mutableStateOf<List<Product>>(emptyList()) }
    var hasSearched by remember { mutableStateOf(false) }

    // 拍照搜物状态
    var showChooser by remember { mutableStateOf(false) }
    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    var cameraUriToLaunch by remember { mutableStateOf<Uri?>(null) }
    var isVisionSearching by remember { mutableStateOf(false) }
    var visionStatus by remember { mutableStateOf("") }
    val context = LocalContext.current
    val visionClient = remember { SseClient() }

    // 启动时从后端拉取真实商品，失败则保留 mock 数据
    LaunchedEffect(Unit) {
        val compareRepo = CompareRepository()
        val real = compareRepo.fetchProducts()
        if (!real.isNullOrEmpty()) {
            allProducts = real
        }
    }

    // 拍照搜物 — 先定义以便 launcher 回调引用
    fun startVisionSearch(imageFile: File) {
        isVisionSearching = true
        visionStatus = "📷 正在识别图片，请稍候…"
        val scope = MainScope()
        scope.launch {
            val visionProducts = mutableListOf<Product>()
            try {
                visionClient.connectVision(imageFile)
                    .collect { event ->
                        when (event) {
                            is SSEEvent.Progress -> {
                                visionStatus = event.message
                            }
                            is SSEEvent.ProductCard -> {
                                visionProducts.add(Product(
                                    productId = event.productId,
                                    title = event.title,
                                    price = event.price,
                                    rating = event.rating.toFloat(),
                                    highlights = event.highlights,
                                    imageUrl = event.imageUrl,
                                    imageUrls = event.imageUrls,
                                    brand = event.brand,
                                    category = event.category,
                                    matchScore = event.matchScore,
                                ))
                            }
                            is SSEEvent.Done -> {
                                if (visionProducts.isNotEmpty()) {
                                    allProducts = (visionProducts + allProducts).distinctBy { it.productId }
                                    searchResults = visionProducts
                                    hasSearched = true
                                }
                                isVisionSearching = false
                                visionStatus = ""
                            }
                            is SSEEvent.Error -> {
                                android.util.Log.e("CompareScreen", "Vision error: ${event.message}")
                                android.widget.Toast.makeText(context, "拍照找货失败，请重试", android.widget.Toast.LENGTH_SHORT).show()
                                isVisionSearching = false
                                visionStatus = ""
                            }
                            else -> {}
                        }
                    }
            } catch (e: Exception) {
                android.util.Log.e("CompareScreen", "Vision exception", e)
                android.widget.Toast.makeText(context, "拍照找货失败，请重试", android.widget.Toast.LENGTH_SHORT).show()
                isVisionSearching = false
                visionStatus = ""
            }
        }
    }

    // 相册选择器
    val galleryPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let {
            try {
                val inputStream = context.contentResolver.openInputStream(it)
                val tempFile = File(context.cacheDir, "compare_gallery_${System.currentTimeMillis()}.jpg")
                inputStream?.use { inp ->
                    tempFile.outputStream().use { out -> inp.copyTo(out) }
                }
                startVisionSearch(tempFile)
            } catch (e: Exception) {
                android.util.Log.e("CompareScreen", "Image save failed", e)
                android.widget.Toast.makeText(context, "图片处理失败，请重试", android.widget.Toast.LENGTH_SHORT).show()
            }
        }
    }

    // 拍照
    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) {
            cameraUri?.let { uri ->
                try {
                    val tempFile = File(context.cacheDir, "compare_camera_${System.currentTimeMillis()}.jpg")
                    context.contentResolver.openInputStream(uri)?.use { inp ->
                        tempFile.outputStream().use { out -> inp.copyTo(out) }
                    }
                    startVisionSearch(tempFile)
                } catch (e: Exception) {
                    android.util.Log.e("CompareScreen", "Camera save failed", e)
                    android.widget.Toast.makeText(context, "拍照处理失败，请重试", android.widget.Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    val launchTakePicture: (Uri) -> Unit = { uri ->
        try {
            cameraUri = uri
            cameraLauncher.launch(uri)
        } catch (e: Exception) {
            android.util.Log.e("CompareScreen", "Camera launch failed", e)
            cameraUri = null
            android.widget.Toast.makeText(context, "拍照搜索启动失败，请稍后重试", android.widget.Toast.LENGTH_SHORT).show()
        }
    }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            cameraUriToLaunch?.let { launchTakePicture(it) }
            cameraUriToLaunch = null
        } else {
            android.widget.Toast.makeText(context, "需要相机权限才能拍照", android.widget.Toast.LENGTH_SHORT).show()
        }
    }

    // 按选中分类过滤（非搜索模式下）
    val categoryProducts by remember {
        derivedStateOf {
            when (selectedCategory) {
                "推荐" -> allProducts
                "全部" -> allProducts
                else -> allProducts.filter { it.category == selectedCategory }
            }
        }
    }

    // 决定显示哪些商品：搜索模式用搜索结果，否则按分类
    val displayProducts = if (hasSearched) searchResults else categoryProducts

    // 本地搜索逻辑
    fun doSearch(query: String) {
        val q = query.trim().lowercase()
        if (q.isEmpty()) return

        val scored = allProducts.map { product ->
            val name = product.title.lowercase()
            val brand = (product.brand ?: "").lowercase()
            val cat = product.category.lowercase()
            var score = 0
            if (name.contains(q)) score += 10
            if (brand.contains(q)) score += 5
            if (cat.contains(q)) score += 3
            // 部分匹配加分
            q.split(" ").forEach { token ->
                if (token.length >= 2) {
                    if (name.contains(token)) score += 3
                    if (brand.contains(token)) score += 2
                }
            }
            product to score
        }.filter { it.second > 0 }
         .sortedByDescending { it.second }
         .map { it.first }

        searchResults = scored.take(10)
        hasSearched = true
        selectedCategory = "推荐"  // 自动切回推荐栏
    }

    Column(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        // ===== 渐变条 =====
        GradientTopBar(
            icons = {
                IconButton(onClick = LocalOnMenuClick.current, modifier = Modifier.size(34.dp)) {
                    Icon(Icons.Default.Menu, "菜单", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(26.dp))
                }
            }
        )

        // ===== 分类标签 =====
        ScrollableTabRow(
            selectedTabIndex = categories.indexOf(selectedCategory).coerceAtLeast(0),
            containerColor = MaterialTheme.colorScheme.surface,
            edgePadding = 16.dp,
            divider = { HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant) }) {
            categories.forEach { cat ->
                val isSelected = cat == selectedCategory
                Tab(selected = isSelected, onClick = {
                    selectedCategory = cat
                    hasSearched = false  // 点击分类退出搜索模式
                },
                    text = {
                        Text(cat,
                            style = if (isSelected) MaterialTheme.typography.titleMedium
                                    else MaterialTheme.typography.bodyMedium,
                            color = if (isSelected) Primary else MaterialTheme.colorScheme.onSurfaceVariant)
                    })
            }
        }

        // ===== 内容区 =====
        Box(modifier = Modifier.weight(1f)) {
            if (isVisionSearching) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(color = Primary)
                        Spacer(Modifier.height(12.dp))
                        Text(visionStatus, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            } else if (selectedProduct != null) {
                // 挂画式价格跟踪面板
                CompareTrackingSheet(
                    productId = selectedProduct!!,
                    onClose = { selectedProduct = null },
                )
            } else {
                CompareProductGrid(
                    products = displayProducts,
                    onProductTap = { selectedProduct = it },
                )
            }
        }

        // ===== 底部搜索输入栏 =====
        CompareSearchBar(
            query = searchQuery,
            onQueryChange = { searchQuery = it },
            onSend = {
                doSearch(searchQuery)
                searchQuery = ""
            },
            placeholder = "搜索商品或粘贴链接…",
            onCameraClick = { showChooser = true },
        )

        // ===== 拍照/相册选择弹窗 =====
        if (showChooser) {
            AlertDialog(
                onDismissRequest = { showChooser = false },
                icon = { Icon(Icons.Default.CameraAlt, contentDescription = null) },
                title = { Text("拍照找货") },
                text = { Text("选择获取图片的方式") },
                confirmButton = {
                    Column {
                        OutlinedButton(
                            onClick = {
                                showChooser = false
                                val dateStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(java.util.Date())
                                val photoFile = File(context.cacheDir, "JPEG_${dateStamp}.jpg")
                                photoFile.createNewFile()
                                val uri = androidx.core.content.FileProvider.getUriForFile(
                                    context,
                                    "${context.packageName}.fileprovider",
                                    photoFile
                                )
                                val hasPermission = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                                if (hasPermission) {
                                    launchTakePicture(uri)
                                } else {
                                    cameraUriToLaunch = uri
                                    cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(20.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("拍照")
                        }
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = {
                                showChooser = false
                                galleryPicker.launch("image/*")
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.PhotoLibrary, contentDescription = null, modifier = Modifier.size(20.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("从相册选择")
                        }
                    }
                },
                dismissButton = {
                    TextButton(onClick = { showChooser = false }) {
                        Text("取消")
                    }
                }
            )
        }
    }
}

// ===== 1:1 复刻主页 ChatInputBar 外观的本地搜索栏 =====
@Composable
private fun CompareSearchBar(
    query: String,
    onQueryChange: (String) -> Unit,
    onSend: () -> Unit,
    placeholder: String,
    onCameraClick: () -> Unit = {},
) {
    Surface(
        shadowElevation = 3.dp,
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.imePadding()
    ) {
        Row(
            Modifier
                .padding(horizontal = Dimens.space3, vertical = Dimens.space2)
                .fillMaxWidth()
                .navigationBarsPadding(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 拍照搜物图标
            IconButton(onClick = onCameraClick, modifier = Modifier.size(44.dp)) {
                Icon(Icons.Default.CameraAlt, "拍照搜物", tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            // 输入框
            OutlinedTextField(
                value = query,
                onValueChange = onQueryChange,
                placeholder = { Text(placeholder, color = MaterialTheme.colorScheme.onSurfaceVariant) },
                textStyle = MaterialTheme.typography.bodyLarge,
                shape = RadiusFull,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = MaterialTheme.colorScheme.outlineVariant,
                    unfocusedContainerColor = MaterialTheme.colorScheme.outlineVariant,
                    focusedBorderColor = Primary,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant
                ),
                modifier = Modifier.weight(1f),
                maxLines = 4
            )
            // 语音输入
            val context = LocalContext.current
            val scope = rememberCoroutineScope()
            val audioClient = remember { AudioClient() }
            var isRecording by remember { mutableStateOf(false) }
            var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
            var recordingFile by remember { mutableStateOf<File?>(null) }

            fun stopAndTranscribe() {
                val activeRecorder = recorder ?: return
                val audioFile = recordingFile ?: return
                try {
                    activeRecorder.stop()
                    activeRecorder.release()
                } catch (e: Exception) {
                    android.util.Log.e("CompareScreen", "Audio recorder stop failed", e)
                    try { activeRecorder.release() } catch (_: Exception) {}
                    android.widget.Toast.makeText(context, "录音时间太短，请重试", android.widget.Toast.LENGTH_SHORT).show()
                    recorder = null
                    recordingFile = null
                    isRecording = false
                    return
                }
                recorder = null
                recordingFile = null
                isRecording = false
                android.widget.Toast.makeText(context, "正在识别语音…", android.widget.Toast.LENGTH_SHORT).show()
                scope.launch {
                    try {
                        val text = audioClient.transcribe(audioFile)
                        if (text.isBlank()) {
                            android.widget.Toast.makeText(context, "没有识别到语音内容", android.widget.Toast.LENGTH_SHORT).show()
                        } else {
                            onQueryChange(text)
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("CompareScreen", "Doubao voice recognition failed", e)
                        android.widget.Toast.makeText(context, "语音识别失败，请检查后端服务", android.widget.Toast.LENGTH_SHORT).show()
                    } finally {
                        audioFile.delete()
                    }
                }
            }

            fun startRecording() {
                try {
                    val audioFile = File(context.cacheDir, "compare_voice_${System.currentTimeMillis()}.m4a")
                    val newRecorder = (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                        MediaRecorder(context)
                    } else {
                        @Suppress("DEPRECATION")
                        MediaRecorder()
                    }).apply {
                        setAudioSource(MediaRecorder.AudioSource.MIC)
                        setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                        setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                        setAudioSamplingRate(16000)
                        setAudioEncodingBitRate(64000)
                        setOutputFile(audioFile.absolutePath)
                        prepare()
                        start()
                    }
                    recordingFile = audioFile
                    recorder = newRecorder
                    isRecording = true
                    android.widget.Toast.makeText(context, "正在录音，再点一次结束", android.widget.Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    android.util.Log.e("CompareScreen", "Audio recorder start failed", e)
                    android.widget.Toast.makeText(context, "录音启动失败，请稍后重试", android.widget.Toast.LENGTH_SHORT).show()
                }
            }

            val voicePermissionLauncher = rememberLauncherForActivityResult(
                ActivityResultContracts.RequestPermission()
            ) { granted ->
                if (granted) {
                    startRecording()
                } else {
                    android.widget.Toast.makeText(context, "需要麦克风权限才能使用语音输入", android.widget.Toast.LENGTH_SHORT).show()
                }
            }

            fun onVoiceClick() {
                if (isRecording) {
                    stopAndTranscribe()
                    return
                }
                val hasPermission = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                if (hasPermission) {
                    startRecording()
                } else {
                    voicePermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                }
            }
            IconButton(
                onClick = { onVoiceClick() },
                modifier = Modifier.size(44.dp)
            ) {
                Icon(
                    Icons.Default.Mic,
                    if (isRecording) "结束录音" else "语音输入",
                    tint = if (isRecording) Primary else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            // 发送按钮
            FilledIconButton(
                onClick = onSend,
                enabled = query.isNotBlank(),
                shape = CircleShape,
                colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = Primary,
                    disabledContainerColor = MaterialTheme.colorScheme.outline
                ),
                modifier = Modifier.size(48.dp)
            ) {
                Icon(Icons.AutoMirrored.Filled.Send, "发送", tint = OnPrimary)
            }
        }
    }
}

// ===== 统一 2 列商品网格 =====
@Composable
private fun CompareProductGrid(
    products: List<com.shopping.agent.data.model.Product>,
    onProductTap: (String) -> Unit,
) {
    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        contentPadding = PaddingValues(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(products, key = { it.productId }) { product ->
            Card(onClick = { onProductTap(product.productId) },
                modifier = Modifier.fillMaxWidth(), shape = RadiusLg,
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column {
                    AsyncImage(model = product.imageUrl,
                        contentDescription = product.title,
                        modifier = Modifier.fillMaxWidth().aspectRatio(1f),
                        contentScale = androidx.compose.ui.layout.ContentScale.Crop)
                    Column(Modifier.padding(12.dp)) {
                        Text(product.title, style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface, maxLines = 2)
                        Spacer(Modifier.height(4.dp))
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text("¥${"%.0f".format(product.price)}", style = PriceMedium,
                                color = TextPrice, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.width(8.dp))
                            if (product.ratingCount > 0) {
                                Text(formatSalesCount(product.ratingCount),
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        }
    }
}

// ===== 挂画式价格跟踪面板 =====
@Composable
private fun CompareTrackingSheet(
    productId: String,
    onClose: () -> Unit,
) {
    var dragOffset by remember { mutableStateOf(0f) }
    val dismissThreshold = 150f

    Surface(
        modifier = Modifier
            .fillMaxSize()
            .pointerInput(Unit) {
                detectVerticalDragGestures(
                    onDragEnd = {
                        if (dragOffset > dismissThreshold) onClose()
                        dragOffset = 0f
                    },
                    onDragCancel = { dragOffset = 0f },
                    onVerticalDrag = { _, amount ->
                        dragOffset = (dragOffset + amount).coerceAtLeast(0f)
                    }
                )
            },
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        color = MaterialTheme.colorScheme.surface,
        shadowElevation = 8.dp,
    ) {
        Column {
            // 拖拽把手 + 上方可点击区域
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onClose() }
                    .padding(vertical = 12.dp),
                contentAlignment = Alignment.Center,
            ) {
                Surface(
                    modifier = Modifier.width(48.dp).height(5.dp),
                    shape = RoundedCornerShape(3.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                ) {}
            }
            // 价格趋势卡片列表
            // TODO: platformTrends 目前使用 MockCompareData，后续需接入真实价格趋势 API
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(MockCompareData.platformTrends) { pt ->
                    PriceTrendCard(
                        platform = pt.platform,
                        lowestPrice = pt.lowestPrice,
                        trend = pt.trend,
                    )
                }
            }
        }

    }
}

@Composable
private fun PriceTrendCard(
    platform: String,
    lowestPrice: Double,
    trend: List<Float>,
) {
    Card(shape = RadiusLg, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(Modifier.size(60.dp), shape = RadiusMd, color = MaterialTheme.colorScheme.outlineVariant) {}
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(platform, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                Spacer(Modifier.height(6.dp))
                PriceTrendChart(trend = trend, modifier = Modifier.fillMaxWidth().height(60.dp))
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    Text("最低价来源: $platform", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("最低价 ¥$lowestPrice", style = MaterialTheme.typography.bodySmall,
                        color = TextPrice, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun PriceTrendChart(
    trend: List<Float>,
    modifier: Modifier = Modifier,
) {
    if (trend.size < 2) return
    val lineColor = TextPrice
    val fillColor = BrandPink.copy(alpha = 0.12f)
    val dotColor = TextPrice
    val axisLabels = listOf("30天前", "15天前", "今天")
    val surfaceColor = MaterialTheme.colorScheme.surface
    val onSurfaceVariant = MaterialTheme.colorScheme.onSurfaceVariant

    Column(modifier = modifier) {
        Canvas(modifier = Modifier.fillMaxWidth().weight(1f)) {
            val w = size.width; val h = size.height
            val maxV = trend.max(); val minV = trend.min()
            val range = (maxV - minV).coerceAtLeast(1f)
            val padLeft = 4f; val padRight = 4f; val padTop = 8f; val padBottom = 4f
            val chartW = w - padLeft - padRight; val chartH = h - padTop - padBottom
            val pts = trend.mapIndexed { i, v ->
                Offset(padLeft + (i.toFloat() / (trend.size - 1)) * chartW,
                       padTop + (1f - (v - minV) / range) * chartH)
            }
            val fillPath = Path().apply {
                moveTo(pts.first().x, h - padBottom)
                pts.forEach { lineTo(it.x, it.y) }
                lineTo(pts.last().x, h - padBottom); close()
            }
            drawPath(fillPath, fillColor)
            val linePath = Path().apply {
                moveTo(pts.first().x, pts.first().y)
                for (i in 1 until pts.size) lineTo(pts[i].x, pts[i].y)
            }
            drawPath(linePath, lineColor, style = Stroke(width = 2.5f * density))
            pts.forEachIndexed { i, pt ->
                if (i == pts.size - 1) {
                    drawCircle(color = surfaceColor, radius = 5f * density, center = pt)
                    drawCircle(color = dotColor, radius = 5f * density, center = pt,
                        style = Stroke(width = 2.5f * density))
                } else drawCircle(color = lineColor, radius = 3f * density, center = pt)
            }
        }
        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween) {
            axisLabels.forEach { label ->
                Text(label, style = MaterialTheme.typography.labelSmall, color = onSurfaceVariant)
            }
        }
    }
}

private fun formatSalesCount(count: Int): String = when {
    count >= 10000 -> "${count / 10000}.${(count % 10000) / 1000}万人付款"
    else -> "${count}人付款"
}
