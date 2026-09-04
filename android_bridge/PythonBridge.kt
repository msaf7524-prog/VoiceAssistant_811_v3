package com.arm.aichat

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import java.io.File

object PythonBridge {

    @Volatile
    private var engine: InferenceEngine? = null

    private fun errorText(e: Throwable): String {
        return "ERROR: ${e.javaClass.simpleName}: ${e.message ?: "Unknown error"}"
    }

    private fun ensureEngine(context: Context): InferenceEngine {
        var current = engine

        if (current == null) {
            synchronized(this) {
                current = engine

                if (current == null) {
                    current = AiChat.getInferenceEngine(
                        context.applicationContext
                    )
                    engine = current
                }
            }
        }

        return current!!
    }

    private suspend fun waitForInitialized(
        target: InferenceEngine,
        timeoutMs: Long = 60000
    ) {
        withTimeout(timeoutMs) {
            while (true) {
                when (val state = target.state.value) {

                    is InferenceEngine.State.Initialized -> {
                        return@withTimeout
                    }

                    is InferenceEngine.State.ModelReady -> {
                        return@withTimeout
                    }

                    is InferenceEngine.State.Error -> {
                        throw state.exception
                    }

                    else -> {
                        delay(50)
                    }
                }
            }
        }
    }

    @JvmStatic
    fun init(context: Context): String {
        return try {

            val target = ensureEngine(context)

            runBlocking {
                waitForInitialized(target)
            }

            "OK"

        } catch (e: Throwable) {
            errorText(e)
        }
    }

    @JvmStatic
    fun copyModelFromUri(
        context: Context,
        uriString: String,
        fileName: String
    ): String {

        return try {

            val modelsDir = File(
                context.filesDir,
                "models"
            )

            if (!modelsDir.exists()) {
                modelsDir.mkdirs()
            }

            val targetFile = File(
                modelsDir,
                fileName
            )

            val uri = Uri.parse(uriString)

            context.contentResolver
                .openInputStream(uri)
                ?.use { input ->

                    targetFile.outputStream()
                        .buffered()
                        .use { output ->

                            input.copyTo(
                                output,
                                1024 * 1024
                            )
                        }

                } ?: throw IllegalStateException(
                "Cannot open selected model"
            )

            if (!targetFile.exists() ||
                targetFile.length() <= 0
            ) {
                throw IllegalStateException(
                    "Model copy failed"
                )
            }

            targetFile.absolutePath

        } catch (e: Throwable) {
            errorText(e)
        }
    }

    @JvmStatic
    fun getModelPath(
        context: Context,
        fileName: String
    ): String {

        return File(
            File(
                context.filesDir,
                "models"
            ),
            fileName
        ).absolutePath
    }

    @JvmStatic
    fun loadModel(
        context: Context,
        modelPath: String
    ): String {

        return try {

            val target = ensureEngine(context)

            runBlocking {

                waitForInitialized(target)

                when (target.state.value) {

                    is InferenceEngine.State.ModelReady -> {
                        target.cleanUp()
                        waitForInitialized(target)
                    }

                    is InferenceEngine.State.Error -> {
                        target.cleanUp()
                        waitForInitialized(target)
                    }

                    else -> Unit
                }

                val file = File(modelPath)

                require(file.exists()) {
                    "Model file not found"
                }

                require(file.isFile) {
                    "Invalid model file"
                }

                require(file.canRead()) {
                    "Model file cannot be read"
                }

                target.loadModel(
                    file.absolutePath
                )
            }

            "OK"

        } catch (e: Throwable) {
            errorText(e)
        }
    }

    @JvmStatic
    fun setSystemPrompt(
        prompt: String
    ): String {

        return try {

            val target = engine
                ?: throw IllegalStateException(
                    "Engine not initialized"
                )

            runBlocking {
                target.setSystemPrompt(
                    prompt
                )
            }

            "OK"

        } catch (e: Throwable) {
            errorText(e)
        }
    }

    @JvmStatic
    fun generate(
        prompt: String,
        maxTokens: Int
    ): String {

        return try {

            val target = engine
                ?: throw IllegalStateException(
                    "Engine not initialized"
                )

            val result = StringBuilder()

            runBlocking {

                target.sendUserPrompt(
                    prompt,
                    maxTokens
                ).collect { token ->

                    result.append(token)
                }
            }

            result.toString()

        } catch (e: Throwable) {
            errorText(e)
        }
    }

    @JvmStatic
    fun getState(): String {

        return try {

            val target = engine
                ?: return "NOT_INITIALIZED"

            target.state.value
                .javaClass
                .simpleName

        } catch (e: Throwable) {
            errorText(e)
        }
    }

    @JvmStatic
    fun cleanUp(): String {

        return try {

            val target = engine
                ?: return "OK"

            when (target.state.value) {

                is InferenceEngine.State.ModelReady,
                is InferenceEngine.State.Error -> {
                    target.cleanUp()
                }

                else -> Unit
            }

            "OK"

        } catch (e: Throwable) {
            errorText(e)
        }
    }
}
