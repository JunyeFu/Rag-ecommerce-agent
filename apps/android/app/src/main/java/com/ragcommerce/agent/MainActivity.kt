package com.ragcommerce.agent

import android.content.ActivityNotFoundException
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
    val audioPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let {
            viewModel.dispatch(
                ShoppingAction.AddAttachment(
                    MediaAttachmentUi(
                        uri = it.toString(),
                        kind = "audio",
                        displayName = it.lastPathSegment ?: "已选音频",
                    ),
                ),
            )
        }
    }
    ShoppingApp(
        state = state,
        onAction = viewModel::dispatch,
        onOpenMerchant = viewModel::openMerchant,
        onSaveProduct = viewModel::saveProduct,
        onAddOffer = viewModel::addOffer,
        onDeleteMyData = viewModel::deleteMyData,
        onQualityDataConsentChanged = viewModel::setQualityDataConsent,
        onPickImage = { imagePicker.launch("image/*") },
        onPickAudio = { audioPicker.launch("audio/*") },
    )
}

@Composable
fun ShoppingApp(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit = {},
    onSaveProduct: (EvidenceProductUi) -> Unit = {},
    onAddOffer: (OfferUi) -> Unit = {},
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
        onDeleteMyData = onDeleteMyData,
        onQualityDataConsentChanged = onQualityDataConsentChanged,
        onPickImage = onPickImage,
        onPickAudio = onPickAudio,
    )
}
