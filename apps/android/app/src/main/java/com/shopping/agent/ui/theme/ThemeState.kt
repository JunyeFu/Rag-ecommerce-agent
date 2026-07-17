package com.shopping.agent.ui.theme

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf

private const val PREFS_NAME = "shopping_theme_prefs"
private const val KEY_DARK_MODE = "dark_mode_enabled"
private const val KEY_DEMO_MODE = "demo_mode_enabled"

/**
 * 全局深色模式状态管理
 * 使用 SharedPreferences 持久化用户选择，确保应用重启后保持用户偏好
 */
class ThemeState(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /** 深色模式开关状态 */
    val isDarkMode: MutableState<Boolean> = mutableStateOf(
        prefs.getBoolean(KEY_DARK_MODE, false)
    )

    /** 切换深色模式并持久化 */
    fun toggleDarkMode(enabled: Boolean) {
        isDarkMode.value = enabled
        prefs.edit().putBoolean(KEY_DARK_MODE, enabled).apply()
    }

    /** 演示模式开关状态 */
    val isDemoMode: MutableState<Boolean> = mutableStateOf(
        prefs.getBoolean(KEY_DEMO_MODE, false)
    )

    /** 切换演示模式并持久化 */
    fun toggleDemoMode(enabled: Boolean) {
        isDemoMode.value = enabled
        prefs.edit().putBoolean(KEY_DEMO_MODE, enabled).apply()
    }
}

/**
 * CompositionLocal 用于在组件树中提供 ThemeState
 * 任意子组件可通过 LocalThemeState.current 获取当前主题状态
 */
val LocalThemeState = staticCompositionLocalOf<ThemeState> {
    error("ThemeState not provided. Make sure to wrap your app with ThemeStateProvider.")
}

/**
 * 在 Composable 中创建并记住 ThemeState 实例
 * 需要在 Activity 级别调用，确保整个应用共享同一个实例
 */
@Composable
fun rememberThemeState(context: Context): ThemeState {
    return remember { ThemeState(context) }
}
