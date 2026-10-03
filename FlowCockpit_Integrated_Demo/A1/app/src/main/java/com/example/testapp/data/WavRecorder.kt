package com.example.testapp.data

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** 16kHz / 單聲道 / PCM16 錄音,停止後輸出 WAV 檔 */
class WavRecorder(private val outFile: File) {
    private var job: Job? = null
    @Volatile private var recording = false

    /** 開始錄音;沒有權限或麥克風無法使用時回傳 false */
    @SuppressLint("MissingPermission") // RECORD_AUDIO 由 MainActivity 先取得
    fun start(scope: CoroutineScope): Boolean {
        if (recording) return false
        val minBuf = AudioRecord.getMinBufferSize(
            RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        val rec = try {
            AudioRecord(
                MediaRecorder.AudioSource.MIC, RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minBuf * 2,
            )
        } catch (e: Exception) {
            return false
        }
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            return false
        }
        try {
            rec.startRecording()
        } catch (e: IllegalStateException) {
            rec.release()
            return false
        }

        recording = true
        job = scope.launch(Dispatchers.IO) {
            val pcm = ByteArrayOutputStream()
            val buf = ByteArray(minBuf)
            while (recording) {
                val n = rec.read(buf, 0, buf.size)
                if (n > 0) pcm.write(buf, 0, n)
            }
            rec.stop()
            rec.release()
            writeWav(pcm.toByteArray())
        }
        return true
    }

    /** 停止並回傳 WAV;沒在錄音或不到 0.3 秒回傳 null */
    suspend fun stop(): File? {
        if (!recording) return null
        recording = false
        job?.join()
        return outFile.takeIf { it.length() > HEADER_BYTES + RATE * 2 * 3 / 10 }
    }

    private fun writeWav(pcm: ByteArray) {
        val header = ByteBuffer.allocate(HEADER_BYTES).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt(36 + pcm.size); put("WAVE".toByteArray())
            put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(1)
            putInt(RATE); putInt(RATE * 2); putShort(2); putShort(16)
            put("data".toByteArray()); putInt(pcm.size)
        }
        outFile.outputStream().use {
            it.write(header.array())
            it.write(pcm)
        }
    }

    private companion object {
        const val RATE = 16_000
        const val HEADER_BYTES = 44
    }
}
