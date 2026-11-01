package com.ragcommerce.agent

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.net.Uri
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Surface
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.annotation.RequiresPermission
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal class VoiceCapture(private val context: Context) {
    private var recorder: AudioRecord? = null
    private var capture: Deferred<Uri>? = null
    private var file: File? = null
    private var keep = false

    @RequiresPermission(Manifest.permission.RECORD_AUDIO)
    @SuppressLint("MissingPermission")
    fun start(scope: CoroutineScope) {
        check(recorder == null)
        val buffer = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        check(buffer > 0) { "麦克风不支持当前录音格式" }
        val audio = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, buffer * 2)
        if (audio.state != AudioRecord.STATE_INITIALIZED) {
            audio.release()
            error("麦克风初始化失败")
        }
        val directory = File(context.cacheDir, "voice-input").apply { mkdirs() }
        val target = File.createTempFile("voice-", ".wav", directory)
        file = target
        recorder = audio
        audio.startRecording()
        capture = scope.async(Dispatchers.IO) {
            val bytes = ByteArray(buffer)
            var length = 0
            RandomAccessFile(target, "rw").use { output ->
                output.write(ByteArray(44))
                while (audio.recordingState == AudioRecord.RECORDSTATE_RECORDING && length < 16000 * 2 * 60) {
                    val count = audio.read(bytes, 0, minOf(bytes.size, 16000 * 2 * 60 - length))
                    if (count < 0) {
                        if (audio.recordingState != AudioRecord.RECORDSTATE_RECORDING) break
                        throw IOException("麦克风读取失败")
                    }
                    if (count > 0) { output.write(bytes, 0, count); length += count }
                }
                if (length == 0) throw IOException("没有录制到音频")
                output.seek(0)
                output.write(wavHeader(length))
            }
            Uri.fromFile(target)
        }
    }

    suspend fun finish(): Uri {
        val audio = requireNotNull(recorder)
        return try {
            audio.stop()
            requireNotNull(capture).await()
        } finally { audio.release(); recorder = null }
    }

    fun retain() { keep = true }

    fun close() {
        recorder?.let { audio ->
            if (audio.recordingState == AudioRecord.RECORDSTATE_RECORDING) audio.stop()
            audio.release()
        }
        recorder = null
        val task = capture
        task?.cancel()
        if (!keep) task?.invokeOnCompletion { file?.delete() }
        if (!keep && task == null) file?.delete()
    }

    companion object {
        fun wavHeader(length: Int): ByteArray = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".toByteArray()).putInt(length + 36).put("WAVEfmt ".toByteArray())
            .putInt(16).putShort(1).putShort(1).putInt(16000).putInt(32000)
            .putShort(2).putShort(16).put("data".toByteArray()).putInt(length).array()
    }
}

@SuppressLint("MissingPermission") // MainActivity opens this dialog only after permission is granted.
@Composable
internal fun VoiceRecordingDialog(onDismiss: () -> Unit, onSend: (Uri) -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    val capture = remember { VoiceCapture(context) }
    var recording by remember { mutableStateOf(false) }
    var processing by remember { mutableStateOf(false) }
    var preview by remember { mutableStateOf<Uri?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var player by remember { mutableStateOf<MediaPlayer?>(null) }
    fun begin() {
        error = null
        try { capture.start(scope); recording = true }
        catch (failure: SecurityException) { capture.close(); error = "没有麦克风权限" }
        catch (failure: IllegalStateException) { capture.close(); error = failure.message }
        catch (failure: IOException) { capture.close(); error = failure.message }
    }
    fun finish() {
        if (!recording || processing) return
        recording = false
        processing = true
        scope.launch {
            try { preview = capture.finish() }
            catch (failure: IOException) { error = failure.message }
            catch (failure: IllegalStateException) { error = failure.message }
            finally { processing = false }
        }
    }
    LaunchedEffect(recording) { if (recording) { delay(60_000); finish() } }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) onDismiss() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); player?.release(); capture.close() }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("用语音说出你的需求") },
        text = {
            Column {
                Text(if (recording) "正在录音，松开后预览 · 最多60秒" else "录音不会自动上传，发送后由模型转写，可修改再继续。")
                error?.let { Text(it) }
                if (preview == null) Surface(
                    color = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                    shape = MaterialTheme.shapes.extraLarge,
                    modifier = Modifier.fillMaxWidth().testTag("voice_hold").semantics {
                        role = Role.Button
                        onClick(label = "开始或停止录音") {
                            if (!processing) { if (recording) finish() else begin() }
                            true
                        }
                    }.pointerInput(Unit) {
                        detectTapGestures(onPress = {
                            if (!processing) begin()
                            tryAwaitRelease()
                            finish()
                        })
                    },
                ) {
                    Box(Modifier.heightIn(min = 48.dp).padding(12.dp), contentAlignment = Alignment.Center) {
                        Text(if (recording) "录音中" else "按住录音")
                    }
                }
                preview?.let { uri -> TextButton(onClick = {
                    player?.release()
                    player = MediaPlayer.create(context, uri)?.apply { start() }
                }, modifier = Modifier.testTag("voice_preview")) { Text("试听录音") } }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.testTag("voice_cancel")) { Text("取消") } },
        confirmButton = { TextButton(onClick = {
            capture.retain()
            preview?.let(onSend)
        }, enabled = preview != null && !processing, modifier = Modifier.testTag("voice_send")) { Text("发送识别") } },
    )
}
