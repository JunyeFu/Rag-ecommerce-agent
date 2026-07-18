package com.shopping.agent.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.shopping.agent.ui.components.HistoryDrawer
import com.shopping.agent.ui.components.MainBottomNavBar
import com.shopping.agent.ui.components.bottomNavItems
import com.shopping.agent.ui.screens.*
import com.shopping.agent.ui.theme.LocalThemeState
import com.shopping.agent.viewmodel.ChatViewModel
import com.shopping.agent.viewmodel.ProductDetailViewModel

private val tabRoutes = bottomNavItems.map { it.route }.toSet()
private val chatRoutes = setOf("home", "explore")

/** CompositionLocal: 各页面可通过它打开历史抽屉 */
val LocalOnMenuClick = staticCompositionLocalOf<() -> Unit> { {} }

@Composable
fun AppNavGraph(
    navController: NavHostController = rememberNavController(),
    startDestination: String = "home",
) {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route
    val isTabRoute = currentRoute in tabRoutes

    var drawerVisible by remember { mutableStateOf(false) }
    val themeState = LocalThemeState.current

    val appViewModelStoreOwner = checkNotNull(LocalViewModelStoreOwner.current) {
        "AppNavGraph requires a ViewModelStoreOwner"
    }
    val shouldInitChat = drawerVisible ||
        currentRoute in chatRoutes ||
        (currentRoute == null && startDestination in chatRoutes)

    // 共享 ChatViewModel（多对话支持）。登录/注册/找回密码页不提前初始化，避免未登录首屏触发聊天 DB/TTS 启动链路。
    // 使用 mutableStateOf 保持 ViewModel 引用，避免导航过渡期 shouldInitChat 切换导致 checkNotNull 崩溃
    val chatViewModelRef = remember { mutableStateOf<ChatViewModel?>(null) }
    if (shouldInitChat) {
        if (chatViewModelRef.value == null) {
            chatViewModelRef.value = viewModel(viewModelStoreOwner = appViewModelStoreOwner)
        }
    }
    // 注意：不在此处将 chatViewModelRef 设为 null — 否则 navigate 到非 chat page 时仍在 backstack 中的 composable("home") 会因 checkNotNull 崩溃
    val chatViewModel = chatViewModelRef.value
    val uiState = chatViewModel?.uiState?.collectAsState()?.value

    CompositionLocalProvider(LocalOnMenuClick provides { drawerVisible = true }) {
        Box {
            Scaffold(
                bottomBar = {
                    if (isTabRoute) {
                        MainBottomNavBar(currentRoute = currentRoute, onNavigate = { route ->
                            navController.navigate(route) {
                                popUpTo("home") { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        })
                    }
                }
            ) { innerPadding ->
                NavHost(navController = navController, startDestination = startDestination,
                    modifier = Modifier.padding(innerPadding)) {
                    composable("home") {
                        HomeScreen(
                            chatViewModel = checkNotNull(chatViewModel),
                            onProductTap = { productId -> navController.navigate("product_detail/$productId") },
                            onCheckoutRequested = {
                                navController.navigate(Screen.Checkout.createRoute("cart"))
                            },
                        )
                    }
                    composable("compare_tab") {
                        CompareTabScreen()
                    }
                    composable("explore") {
                        ExploreScreen(
                            chatViewModel = checkNotNull(chatViewModel),
                            onChatSend = { navController.navigate("home") {
                                popUpTo("home") { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }},
                            onPostClick = { postId ->
                                navController.navigate("explore_post/$postId")
                            }
                        )
                    }
                    composable("profile") {
                        val ctx = androidx.compose.ui.platform.LocalContext.current
                        val repo = remember { com.shopping.agent.data.local.UserRepository(ctx) }
                        ProfileScreen(
                            onSettingsClick = { navController.navigate("settings") },
                            onCustomerServiceClick = { navController.navigate("customer_service") },
                            onCartClick = {
                                navController.navigate(Screen.Cart.route) {
                                    popUpTo("home") { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            onFavoritesClick = { navController.navigate(Screen.Favorites.route) },
                            onFootprintsClick = { navController.navigate(Screen.Footprints.route) },
                            onOrdersClick = { statusFilter ->
                                navController.navigate(Screen.Orders.createRoute(statusFilter))
                            },
                        )
                    }
                    composable(Screen.Cart.route) {
                        CartScreen(
                            onCheckout = { navController.navigate(Screen.Checkout.createRoute("cart")) },
                            onNavigateToHome = {
                                navController.navigate("home") {
                                    popUpTo("home") { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                        )
                    }
                    composable(
                        Screen.Checkout.route,
                        arguments = listOf(
                            navArgument("source") { type = NavType.StringType },
                            navArgument("productId") { type = NavType.StringType },
                        ),
                    ) { entry ->
                        CheckoutScreen(
                            source = entry.arguments?.getString("source") ?: "cart",
                            productId = entry.arguments?.getString("productId")?.takeIf { it != "_" },
                            onBack = { navController.popBackStack() },
                            onAddAddress = { navController.navigate("shipping_address") },
                            onOrderCreated = { orderId ->
                                navController.navigate(Screen.OrderDetail.createRoute(orderId)) {
                                    popUpTo(Screen.Cart.route) { inclusive = false }
                                }
                            },
                        )
                    }
                    composable(
                        Screen.OrderDetail.route,
                        arguments = listOf(navArgument("orderId") { type = NavType.StringType }),
                    ) { entry ->
                        OrderDetailScreen(
                            orderId = entry.arguments?.getString("orderId") ?: "",
                            onBack = { navController.popBackStack() },
                        )
                    }
                    composable("settings") {
                        val ctx = androidx.compose.ui.platform.LocalContext.current
                        val repo = remember { com.shopping.agent.data.local.UserRepository(ctx) }
                        val scope = rememberCoroutineScope()

                        /** 检查游客状态，游客则跳转登录页，否则执行目标导航 */
                        fun guardedNavigate(route: String) {
                            scope.launch {
                                val isGuest = try {
                                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                        repo.isGuestUser()
                                    }
                                } catch (_: Exception) { true }
                                if (isGuest) {
                                    android.widget.Toast.makeText(ctx, "请先登录后再使用此功能", android.widget.Toast.LENGTH_SHORT).show()
                                    navController.navigate("login")
                                } else {
                                    navController.navigate(route)
                                }
                            }
                        }

                        SettingsScreen(
                            onBack = { navController.popBackStack() },
                            onNavigateToProfileEdit = { navController.navigate("profile_edit") },
                            onNavigateToShippingAddress = { guardedNavigate("shipping_address") },
                            onNavigateToPaymentSettings = { guardedNavigate("payment_settings") },
                            onNavigateToCountryRegion = { guardedNavigate("country_region") },
                            onSwitchAccount = {
                                scope.launch {
                                    try {
                                        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                            repo.deleteCredentials()
                                        }
                                    } catch (_: Exception) {}
                                    navController.navigate("login")
                                }
                            },
                            onLogout = {
                                scope.launch {
                                    try {
                                        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                            repo.clearAllLocalData()
                                            repo.deleteCredentials()
                                        }
                                    } catch (_: Exception) {}
                                    navController.navigate("login") {
                                        popUpTo("home") { inclusive = true }
                                        launchSingleTop = true
                                    }
                                }
                            },
                            isDemoMode = themeState.isDemoMode.value,
                            onDemoModeChange = { themeState.toggleDemoMode(it) },
                        )
                    }
                    composable("profile_edit") {
                        ProfileEditScreen(onBack = { navController.popBackStack() })
                    }
                    composable("customer_service") {
                        CustomerServiceScreen(onBack = { navController.popBackStack() })
                    }
                    composable(Screen.Favorites.route) {
                        FavoritesScreen(
                            onBack = { navController.popBackStack() },
                            onProductClick = { productId ->
                                navController.navigate(Screen.ProductDetail.createRoute(productId))
                            },
                        )
                    }
                    composable(Screen.Footprints.route) {
                        FootprintsScreen(
                            onBack = { navController.popBackStack() },
                            onProductClick = { productId ->
                                navController.navigate(Screen.ProductDetail.createRoute(productId))
                            },
                        )
                    }
                    composable(
                        Screen.Orders.route,
                        arguments = listOf(navArgument("statusFilter") {
                            type = NavType.StringType
                            defaultValue = ""
                        }),
                    ) { entry ->
                        OrdersScreen(
                            statusFilter = entry.arguments?.getString("statusFilter") ?: "",
                            onBack = { navController.popBackStack() },
                            onProductClick = { productId ->
                                navController.navigate(Screen.ProductDetail.createRoute(productId))
                            },
                            onBuyAgain = {
                                // 先退出订单页面返回上一级，再进入购物车页面（购物车不能是订单的子页面）
                                navController.popBackStack()
                                navController.navigate(Screen.Cart.route) {
                                    popUpTo("home") { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            onReview = { orderId, _, _, _, _ ->
                                navController.navigate(Screen.Review.createRoute(orderId))
                            },
                        )
                    }
                    // 评价晒单页面
                    composable(
                        Screen.Review.route,
                        arguments = listOf(navArgument("orderId") { type = NavType.LongType }),
                    ) { entry ->
                        ReviewScreen(
                            orderId = entry.arguments?.getLong("orderId") ?: 0,
                            onBack = { navController.popBackStack() },
                            onPublishSuccess = { navController.popBackStack() },
                        )
                    }
                    composable("shipping_address") {
                        ShippingAddressScreen(onBack = { navController.popBackStack() })
                    }
                    composable("payment_settings") {
                        PaymentSettingsScreen(onBack = { navController.popBackStack() })
                    }
                    composable("country_region") {
                        CountryRegionScreen(onBack = { navController.popBackStack() })
                    }
                    composable("login") {
                        LoginScreen(
                            onBack = {
                                // 如果登录页是启动目标（首次启动未登录），不允许通过返回键离开
                                if (navController.previousBackStackEntry != null) {
                                    navController.popBackStack()
                                }
                            },
                            onLoginSuccess = {
                                navController.navigate("home") {
                                    popUpTo("login") { inclusive = true }
                                    launchSingleTop = true
                                }
                            },
                            onNavigateToRegister = { navController.navigate("register") },
                            onNavigateToForgotPassword = { navController.navigate("forgot_password") },
                            onGuestLogin = {
                                navController.navigate("home") {
                                    popUpTo("login") { inclusive = true }
                                    launchSingleTop = true
                                }
                            },
                        )
                    }
                    composable("register") {
                        RegisterScreen(
                            onBack = { navController.popBackStack() },
                            onRegisterSuccess = { navController.popBackStack() },
                        )
                    }
                    composable("forgot_password") {
                        ForgotPasswordScreen(
                            onBack = { navController.popBackStack() },
                            onNavigateToPasswordReset = { account ->
                                navController.navigate("password_reset/$account")
                            },
                        )
                    }
                    composable("password_reset/{account}",
                        arguments = listOf(navArgument("account") { type = NavType.StringType })) { entry ->
                        PasswordResetScreen(
                            onBack = { navController.popBackStack() },
                            onResetSuccess = {
                                navController.navigate("login") {
                                    popUpTo("login") { inclusive = true }
                                    launchSingleTop = true
                                }
                            },
                            account = entry.arguments?.getString("account") ?: "",
                        )
                    }
                    composable("category_list") { CategoryListScreen(navController = navController) }
                    composable("explore_post/{postId}",
                        arguments = listOf(navArgument("postId") { type = NavType.StringType })) { entry ->
                        ExploreProductPostScreen(
                            postId = entry.arguments?.getString("postId") ?: "",
                            onBack = { navController.popBackStack() }
                        )
                    }
                    composable("product_detail/{productId}",
                        arguments = listOf(navArgument("productId") { type = NavType.StringType })) { entry ->
                        val detailViewModel: ProductDetailViewModel = viewModel(
                            viewModelStoreOwner = entry
                        )
                        val productId = entry.arguments?.getString("productId") ?: ""
                        val ctx = androidx.compose.ui.platform.LocalContext.current
                        val repo = remember { com.shopping.agent.data.local.UserRepository(ctx) }

                        // 进入商品详情页时记录浏览足迹（两个数据库）
                        LaunchedEffect(productId) {
                            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                repo.recordFootprint(productId)
                                repo.syncFootprintToBackend(productId)
                            }
                        }

                        ProductDetailScreen(
                            productId = productId,
                            onBack = { navController.popBackStack() },
                            onBuyNow = { pid ->
                                navController.navigate(Screen.Checkout.createRoute("buy", pid))
                            },
                            onCustomerServiceClick = { navController.navigate("customer_service") },
                            viewModel = detailViewModel,
                        )
                    }
                }
            }

            if (chatViewModel != null && uiState != null) {
                // 挂画式历史侧边栏 — 真实数据
                HistoryDrawer(
                    visible = drawerVisible,
                    onDismiss = { drawerVisible = false },
                    conversations = uiState!!.conversations,
                    currentConversationId = uiState!!.currentConversationId,
                    onSessionClick = { convId ->
                        chatViewModel.loadConversation(convId)
                    },
                    onNewChat = {
                        chatViewModel.createNewConversation()
                    },
                    onDeleteConversation = { convId ->
                        chatViewModel.deleteConversation(convId)
                    },
                    onProfileClick = {
                        drawerVisible = false
                        navController.navigate("profile") {
                            popUpTo("home") { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                )
            }
        }
    }
}
