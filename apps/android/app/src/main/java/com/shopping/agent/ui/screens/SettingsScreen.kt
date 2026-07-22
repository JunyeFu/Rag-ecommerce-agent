package com.shopping.agent.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.Help
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shopping.agent.ui.components.GradientTopBar
import com.shopping.agent.ui.theme.*

@Composable
fun SettingsScreen(
    onBack: () -> Unit = {},
    onNavigateToProfileEdit: () -> Unit = {},
    onNavigateToShippingAddress: () -> Unit = {},
    onNavigateToPaymentSettings: () -> Unit = {},
    onNavigateToCountryRegion: () -> Unit = {},
    onSwitchAccount: () -> Unit = {},
    onLogout: () -> Unit = {},
    isDemoMode: Boolean = false,
    onDemoModeChange: (Boolean) -> Unit = {},
) {
    Column(
        modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
    ) {
        // 渐变条 (对齐全局设计系统)
        GradientTopBar(icons = {
            IconButton(onClick = onBack, modifier = Modifier.size(34.dp)) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(26.dp))
            }
            Text("设置", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f).padding(start = 4.dp))
            // 通知角标
//            BadgedBox(badge = { Badge(containerColor = Warning) { Text("3", style = MaterialTheme.typography.labelSmall, color = OnPrimary) } }) {
//                IconButton(onClick = {}, modifier = Modifier.size(34.dp)) {
//                    Icon(Icons.Default.Notifications, "通知", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(26.dp))
//                }
//            }
            IconButton(onClick = {}, modifier = Modifier.size(34.dp)) {
                Icon(Icons.Default.MoreVert, "更多", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(26.dp))
            }
        })

        // 内容区
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // 分组1: 账号与安全
            SettingsSectionCard("账号与安全") {
                SettingsRow(Icons.Default.Person, "个人信息", onClick = onNavigateToProfileEdit)
                SettingsDivider()
                SettingsRow(Icons.Default.LocationOn, "收货地址", onClick = onNavigateToShippingAddress)
                SettingsDivider()
                SettingsRow(Icons.Default.AccountBalanceWallet, "支付设置", onClick = onNavigateToPaymentSettings)
                SettingsDivider()
                SettingsRow(Icons.Default.Language, "国家与地区", "中国", onClick = onNavigateToCountryRegion)
            }

            // 分组2: 功能
            SettingsSectionCard("功能") {
                SettingsRow(Icons.Default.DarkMode, "深色模式", onClick = {}, trailing = {
                    val themeState = LocalThemeState.current
                    Switch(
                        checked = themeState.isDarkMode.value,
                        onCheckedChange = { themeState.toggleDarkMode(it) }
                    )
                })
                SettingsDivider()
                SettingsRow(Icons.Default.Science, "演示模式", onClick = {}, trailing = {
                    Switch(
                        checked = isDemoMode,
                        onCheckedChange = onDemoModeChange
                    )
                })
            }

            Spacer(Modifier.height(8.dp))

            // 法律链接
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                listOf("个人信息共享清单", "个人信息收集清单", "证照信息").forEach { link ->
                    Text(link, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.clickable {})
                }
            }

            Spacer(Modifier.height(12.dp))

            // 底部按钮
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = onSwitchAccount, modifier = Modifier.weight(1f), shape = RadiusLg,
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = MaterialTheme.colorScheme.surface, contentColor = BrandPink),
                    border = BorderStroke(1.dp, BrandPink.copy(alpha = 0.5f)),
                ) { Text("切换账号", modifier = Modifier.padding(vertical = 4.dp)) }
                OutlinedButton(onClick = onLogout, modifier = Modifier.weight(1f), shape = RadiusLg,
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = MaterialTheme.colorScheme.surface, contentColor = MaterialTheme.colorScheme.onSurfaceVariant),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                ) { Text("退出登录", modifier = Modifier.padding(vertical = 4.dp)) }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}

// ── 复用组件 ──

@Composable
private fun SettingsSectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(shape = RadiusLg, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)) {
        Column {
            Text(title, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp))
            content()
        }
    }
}

@Composable
private fun SettingsRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    value: String? = null,
    valueColor: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    onClick: () -> Unit,
    trailing: (@Composable () -> Unit)? = null,
) {
    Row(modifier = Modifier.fillMaxWidth().clickable { onClick() }
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = title, tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(12.dp))
        Text(title, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurface, modifier = Modifier.weight(1f))
        if (value != null) {
            Text(value, style = MaterialTheme.typography.bodySmall, color = valueColor)
            Spacer(Modifier.width(4.dp))
        }
        if (trailing != null) {
            trailing()
            Spacer(Modifier.width(4.dp))
        }
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, "进入", tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(20.dp))
    }
}

@Composable
private fun SettingsDivider() {
    HorizontalDivider(modifier = Modifier.padding(horizontal = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
}
