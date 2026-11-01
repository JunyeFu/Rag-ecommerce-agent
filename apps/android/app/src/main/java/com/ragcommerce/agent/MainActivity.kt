package com.ragcommerce.agent

import android.content.ActivityNotFoundException
import android.Manifest
import android.content.pm.PackageManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.core.content.ContextCompat
import androidx.compose.ui.platform.LocalContext
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.MediaAttachmentUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingUiState
import com.ragcommerce.agent.ui.ShoppingViewModel
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ShoppingRoute() }
    }
}

@Composable
private fun ShoppingRoute(viewModel: ShoppingViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var voiceDialog by remember { mutableStateOf(false) }
    val microphonePermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) voiceDialog = true
        else viewModel.dispatch(ShoppingAction.TurnFailed("未获得麦克风权限，你可以继续输入文字或选择图片"))
    }
    LaunchedEffect(viewModel) {
        viewModel.merchantLinks.collect { link ->
            try {
                context.startActivity(
                    Intent(Intent.ACTION_VIEW, Uri.parse(link))
                        .addCategory(Intent.CATEGORY_BROWSABLE),
                )
            } catch (_: ActivityNotFoundException) {
                viewModel.reportMerchantLaunchFailure()
            }
        }
    }
    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let {
            viewModel.dispatch(
                ShoppingAction.AddAttachment(
                    MediaAttachmentUi(
                        uri = it.toString(),
                        kind = "image",
                        displayName = it.lastPathSegment ?: "已选图片",
                    ),
                ),
            )
        }
    }
    if (voiceDialog) VoiceRecordingDialog(onDismiss = { voiceDialog = false }, onSend = { uri ->
        voiceDialog = false
        viewModel.dispatch(ShoppingAction.AddAttachment(MediaAttachmentUi(uri.toString(), "audio", "刚录制的购买需求")))
        viewModel.dispatch(ShoppingAction.SubmitMission)
    })
    ShoppingApp(
        state = state,
        onAction = viewModel::dispatch,
        onOpenMerchant = viewModel::openMerchant,
        onSaveProduct = viewModel::saveProduct,
        onAddOffer = viewModel::addOffer,
        onCreateWatcher = viewModel::createWatcher,
        onDeleteMyData = viewModel::deleteMyData,
        onQualityDataConsentChanged = viewModel::setQualityDataConsent,
        onPickImage = { imagePicker.launch("image/*") },
        onPickAudio = {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) voiceDialog = true
            else microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
        },
    )
}

@Composable
fun ShoppingApp(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit = {},
    onSaveProduct: (EvidenceProductUi) -> Unit = {},
    onAddOffer: (OfferUi) -> Unit = {},
    onCreateWatcher: (OfferUi, String) -> Unit = { _, _ -> },
    onDeleteMyData: () -> Unit = {},
    onQualityDataConsentChanged: (Boolean) -> Unit = {},
    onPickImage: () -> Unit = {},
    onPickAudio: () -> Unit = {},
) {
    EditorialShoppingApp(
        state = state,
        onAction = onAction,
        onOpenMerchant = onOpenMerchant,
        onSaveProduct = onSaveProduct,
        onAddOffer = onAddOffer,
        onCreateWatcher = onCreateWatcher,
        onDeleteMyData = onDeleteMyData,
        onQualityDataConsentChanged = onQualityDataConsentChanged,
        onPickImage = onPickImage,
        onPickAudio = onPickAudio,
    )
}
