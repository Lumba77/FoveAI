"""
Gemma4ChatHandler — extracted from llama-cpp-python 0.3.34
Works with llama-cpp-python 0.3.16 (which has mtmd_cpp but not the handler class)
"""

import ctypes
import json
import os
import sys
from collections.abc import Iterator
from contextlib import ExitStack
from typing import (
    Any,
    Literal,
    Union,
)

import jinja2
import llama_cpp
from jinja2.sandbox import ImmutableSandboxedEnvironment
from llama_cpp import llama, llama_grammar, llama_types
from llama_cpp.llama_chat_format import (
    Jinja2ChatFormatter,
    _convert_completion_to_chat,
    _convert_completion_to_chat_function,
    _grammar_for_response_format,
    suppress_stdout_stderr,
)

try:
    from llama_cpp.llama_chat_format import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class MTMDChatHandler:
    def __init__(
        self, clip_model_path: str, verbose: bool = True, use_gpu: bool = True
    ):
        from llama_cpp import mtmd_cpp

        self.clip_model_path = clip_model_path
        self.verbose = verbose
        self.use_gpu = use_gpu
        self._mtmd_cpp = mtmd_cpp
        self._exit_stack = ExitStack()
        self.mtmd_ctx: mtmd_cpp.mtmd_context_p | None = None

        if not os.path.exists(clip_model_path):
            raise ValueError(f"Clip model path does not exist: {clip_model_path}")

    def _init_mtmd_context(self, llama_model: llama.Llama):
        self.verbose = llama_model.verbose
        if self.mtmd_ctx is not None:
            return

        with suppress_stdout_stderr(disable=self.verbose):
            ctx_params = self._mtmd_cpp.mtmd_context_params_default()
            ctx_params.use_gpu = self.use_gpu
            ctx_params.print_timings = self.verbose
            ctx_params.n_threads = llama_model.n_threads
            ctx_params.flash_attn_type = (
                llama_cpp.LLAMA_FLASH_ATTN_TYPE_ENABLED
                if (
                    llama_model.context_params.flash_attn_type
                    == llama_cpp.LLAMA_FLASH_ATTN_TYPE_ENABLED
                )
                else llama_cpp.LLAMA_FLASH_ATTN_TYPE_DISABLED
            )

            self.mtmd_ctx = self._mtmd_cpp.mtmd_init_from_file(
                self.clip_model_path.encode(), llama_model.model, ctx_params
            )

            if self.mtmd_ctx is None:
                raise ValueError(
                    f"Failed to load mtmd context from: {self.clip_model_path}"
                )

            if not self._mtmd_cpp.mtmd_support_vision(self.mtmd_ctx):
                raise ValueError("Vision is not supported by this model")

            def mtmd_free():
                with suppress_stdout_stderr(disable=self.verbose):
                    if self.mtmd_ctx is not None:
                        self._mtmd_cpp.mtmd_free(self.mtmd_ctx)
                        self.mtmd_ctx = None

            self._exit_stack.callback(mtmd_free)

    def load_image(self, image_url: str) -> bytes:
        return self._load_image(image_url)

    def load_audio(self, audio_url: str) -> bytes:
        return self._load_image(audio_url)  # same data: URL / HTTP loading logic

    def _create_audio_bitmap_from_samples(self, n_samples: int, samples: Any):
        """Create an MTMD audio bitmap from float samples."""
        if self.mtmd_ctx is None:
            raise ValueError("mtmd context not initialized")
        with suppress_stdout_stderr(disable=self.verbose):
            bitmap = self._mtmd_cpp.mtmd_bitmap_init_from_audio(
                n_samples,
                samples,
            )
            if bitmap is None:
                raise ValueError("Failed to create audio bitmap from samples")
            return bitmap

    def _decode_audio_to_floats(self, audio_bytes: bytes):
        """Decode audio bytes (WAV/MP3/etc) into a float32 array at the model's native sample rate."""
        import io
        import wave

        # Get the model's expected sample rate
        target_sr = self._mtmd_cpp.mtmd_get_audio_sample_rate(self.mtmd_ctx)
        if target_sr <= 0:
            target_sr = 16000  # fallback

        # Try wave module first (WAV format)
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                n_channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                framerate = wav.getframerate()
                n_frames = wav.getnframes()
                raw = wav.readframes(n_frames)
        except Exception:
            # Try soundfile (handles FLAC, OGG, etc)
            try:
                import soundfile as sf

                samples, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
                # Ensure mono
                if len(samples.shape) > 1:
                    samples = samples.mean(axis=1)
                # Resample if needed
                if sr != target_sr:
                    samples = self._resample(samples, sr, target_sr)
                return samples.tolist(), len(samples)
            except ImportError:
                # Try numpy + manual decode as last resort
                try:
                    import numpy as np

                    with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                        n_channels = wav.getnchannels()
                        sampwidth = wav.getsampwidth()
                        framerate = wav.getframerate()
                        n_frames = wav.getnframes()
                        raw = wav.readframes(n_frames)
                except Exception:
                    raise ValueError(
                        "Cannot decode audio — install soundfile: pip install soundfile"
                    )

        # Convert raw bytes to float32 samples
        import numpy as np

        if sampwidth == 2:
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 1:
            audio = (
                np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128
            ) / 128.0
        elif sampwidth == 4:
            audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported sample width: {sampwidth}")

        # Convert to mono
        if n_channels > 1:
            audio = audio[::n_channels]

        # Resample if needed
        if framerate != target_sr:
            audio = self._resample(audio, framerate, target_sr)

        return audio.tolist(), len(audio)

    @staticmethod
    def _resample(samples, orig_sr, target_sr):
        """Simple linear resampling."""
        import numpy as np

        if orig_sr == target_sr:
            return samples
        ratio = target_sr / orig_sr
        n_orig = len(samples)
        n_new = int(n_orig * ratio)
        indices = np.linspace(0, n_orig - 1, n_new)
        return np.interp(indices, np.arange(n_orig), samples).astype(np.float32)

    def _create_bitmap_from_bytes(self, image_bytes: bytes):
        if self.mtmd_ctx is None:
            raise ValueError("mtmd context not initialized")

        with suppress_stdout_stderr(disable=self.verbose):
            bitmap = self._mtmd_cpp.mtmd_helper_bitmap_init_from_buf(
                self.mtmd_ctx,
                (ctypes.c_uint8 * len(image_bytes)).from_buffer(bytearray(image_bytes)),
                len(image_bytes),
                False,
            )

            if bitmap is None:
                raise ValueError("Failed to create bitmap from image bytes")

            return bitmap

    def _get_chat_template(self, llama_model: llama.Llama) -> str:
        chat_template = llama_model.metadata.get("tokenizer.chat_template")
        if not isinstance(chat_template, str) or chat_template == "":
            raise ValueError(
                f"{self.__class__.__name__} requires tokenizer.chat_template metadata"
            )
        return chat_template

    def _get_template_messages(
        self,
        messages: list[llama_types.ChatCompletionRequestMessage],
        media_marker: str,
    ) -> list[Any]:
        return [
            self._convert_message_for_template(message, media_marker)
            for message in messages
        ]

    @classmethod
    def _convert_message_for_template(
        cls,
        message: llama_types.ChatCompletionRequestMessage,
        media_marker: str,
    ) -> dict[str, Any]:
        message_dict = dict(message)
        content = message_dict.get("content")
        if isinstance(content, list):
            message_dict["content"] = [
                cls._convert_content_part_for_template(part, media_marker)
                for part in content
            ]
        return message_dict

    @staticmethod
    def _convert_content_part_for_template(
        part: Any,
        media_marker: str,
    ) -> Any:
        if isinstance(part, dict) and part.get("type") in ("image_url", "audio_url"):
            return {"type": "text", "text": media_marker}
        return part

    @staticmethod
    def _decode_token_piece(piece: Any) -> str:
        if isinstance(piece, bytes):
            return piece.decode("utf-8", errors="ignore")
        return str(piece)

    def _postprocess_template_text(
        self,
        text: str,
        image_urls: list[str],
        media_marker: str,
        audio_urls: list[str] | None = None,
    ) -> str:
        for image_url in image_urls:
            text = text.replace(image_url, media_marker)
        if audio_urls:
            for audio_url in audio_urls:
                text = text.replace(audio_url, media_marker)
        return text

    def __call__(
        self,
        *,
        llama: llama.Llama,
        messages: list[llama_types.ChatCompletionRequestMessage],
        functions: list[llama_types.ChatCompletionFunction] | None = None,
        function_call: llama_types.ChatCompletionRequestFunctionCall | None = None,
        tools: list[llama_types.ChatCompletionTool] | None = None,
        tool_choice: llama_types.ChatCompletionToolChoiceOption | None = None,
        temperature: float = 0.2,
        top_p: float = 0.95,
        top_k: int = 40,
        min_p: float = 0.05,
        typical_p: float = 1.0,
        stream: bool = False,
        stop: str | list[str] | None = [],
        seed: int | None = None,
        response_format: llama_types.ChatCompletionRequestResponseFormat | None = None,
        max_tokens: int | None = None,
        presence_penalty: float = 0.0,
        frequency_penalty: float = 0.0,
        repeat_penalty: float = 1.1,
        tfs_z: float = 1.0,
        mirostat_mode: int = 0,
        mirostat_tau: float = 5.0,
        mirostat_eta: float = 0.1,
        model: str | None = None,
        logits_processor: llama.LogitsProcessorList | None = None,
        grammar: llama.LlamaGrammar | None = None,
        logit_bias: dict[str, float] | None = None,
        logprobs: bool | None = None,
        top_logprobs: int | None = None,
        **kwargs,  # type: ignore
    ) -> llama_types.CreateChatCompletionResponse | Iterator[llama_types.CreateChatCompletionStreamResponse]:
        self._init_mtmd_context(llama)
        assert self.mtmd_ctx is not None

        image_urls = self.get_image_urls(messages)
        audio_urls = self.get_audio_urls(messages)
        media_marker = self._mtmd_cpp.mtmd_default_marker().decode("utf-8")
        template_env = ImmutableSandboxedEnvironment(
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=[
                Jinja2ChatFormatter.IgnoreGenerationTags,
                jinja2.ext.loopcontrols,
            ],
        )
        template_env.filters["tojson"] = Jinja2ChatFormatter.tojson
        template = template_env.from_string(self._get_chat_template(llama))

        def raise_exception(message: str):
            raise ValueError(message)

        text = template.render(
            messages=self._get_template_messages(messages, media_marker),
            add_generation_prompt=True,
            eos_token=self._decode_token_piece(llama.detokenize([llama.token_eos()])),
            bos_token=self._decode_token_piece(llama.detokenize([llama.token_bos()])),
            raise_exception=raise_exception,
            functions=functions,
            function_call=function_call,
            tools=tools,
            tool_choice=tool_choice,
            strftime_now=Jinja2ChatFormatter.strftime_now,
            **kwargs,
        )
        text = self._postprocess_template_text(
            text, image_urls, media_marker, audio_urls
        )

        if self.verbose:
            print(text, file=sys.stderr)

        bitmaps = []
        bitmap_cleanup = []
        try:
            for image_url in image_urls:
                image_bytes = self.load_image(image_url)
                bitmap = self._create_bitmap_from_bytes(image_bytes)
                bitmaps.append(bitmap)
                bitmap_cleanup.append(bitmap)

            # Load audio URLs and create audio bitmaps
            for audio_url in audio_urls:
                audio_bytes = self.load_audio(audio_url)
                samples, n_samples = self._decode_audio_to_floats(audio_bytes)
                float_array = (ctypes.c_float * n_samples)(*samples)
                bitmap = self._create_audio_bitmap_from_samples(n_samples, float_array)
                bitmaps.append(bitmap)
                bitmap_cleanup.append(bitmap)

            input_text = self._mtmd_cpp.mtmd_input_text()
            input_text.text = text.encode("utf-8")
            input_text.add_special = True
            input_text.parse_special = True

            chunks = self._mtmd_cpp.mtmd_input_chunks_init()
            if chunks is None:
                raise ValueError("Failed to create input chunks")

            try:
                bitmap_array = (self._mtmd_cpp.mtmd_bitmap_p_ctypes * len(bitmaps))(
                    *bitmaps
                )
                result = self._mtmd_cpp.mtmd_tokenize(
                    self.mtmd_ctx,
                    chunks,
                    ctypes.byref(input_text),
                    bitmap_array,
                    len(bitmaps),
                )

                if result != 0:
                    raise ValueError(f"Failed to tokenize input: error code {result}")

                llama.reset()
                llama._ctx.kv_cache_clear()

                n_chunks = self._mtmd_cpp.mtmd_input_chunks_size(chunks)

                for i in range(n_chunks):
                    chunk = self._mtmd_cpp.mtmd_input_chunks_get(chunks, i)
                    if chunk is None:
                        continue

                    chunk_type = self._mtmd_cpp.mtmd_input_chunk_get_type(chunk)

                    if chunk_type == self._mtmd_cpp.MTMD_INPUT_CHUNK_TYPE_TEXT:
                        n_tokens_out = ctypes.c_size_t()
                        tokens_ptr = self._mtmd_cpp.mtmd_input_chunk_get_tokens_text(
                            chunk, ctypes.byref(n_tokens_out)
                        )

                        if tokens_ptr and n_tokens_out.value > 0:
                            tokens = [tokens_ptr[j] for j in range(n_tokens_out.value)]

                            if llama.n_tokens + len(tokens) > llama.n_ctx():
                                raise ValueError(
                                    f"Prompt exceeds n_ctx: {llama.n_tokens + len(tokens)} > {llama.n_ctx()}"
                                )
                            llama.eval(tokens)

                    elif chunk_type in [
                        self._mtmd_cpp.MTMD_INPUT_CHUNK_TYPE_IMAGE,
                        self._mtmd_cpp.MTMD_INPUT_CHUNK_TYPE_AUDIO,
                    ]:
                        chunk_n_tokens = self._mtmd_cpp.mtmd_input_chunk_get_n_tokens(
                            chunk
                        )

                        if llama.n_tokens + chunk_n_tokens > llama.n_ctx():
                            raise ValueError(
                                f"Prompt exceeds n_ctx: {llama.n_tokens + chunk_n_tokens} > {llama.n_ctx()}"
                            )

                        new_n_past = llama_cpp.llama_pos(0)
                        result = self._mtmd_cpp.mtmd_helper_eval_chunk_single(
                            self.mtmd_ctx,
                            llama._ctx.ctx,
                            chunk,
                            llama_cpp.llama_pos(llama.n_tokens),
                            llama_cpp.llama_seq_id(0),
                            llama.n_batch,
                            False,  # logits_last
                            ctypes.byref(new_n_past),
                        )

                        if result != 0:
                            raise ValueError(
                                f"Failed to evaluate chunk: error code {result}"
                            )

                        llama.n_tokens = new_n_past.value

                prompt = llama.input_ids[: llama.n_tokens].tolist()

            finally:
                self._mtmd_cpp.mtmd_input_chunks_free(chunks)

        finally:
            for bitmap in bitmap_cleanup:
                self._mtmd_cpp.mtmd_bitmap_free(bitmap)

        if response_format is not None and response_format["type"] == "json_object":
            grammar = _grammar_for_response_format(response_format)

        if functions is not None:
            tools = [
                {
                    "type": "function",
                    "function": function,
                }
                for function in functions
            ]

        if function_call is not None:
            if isinstance(function_call, str) and (
                function_call == "none" or function_call == "auto"
            ):
                tool_choice = function_call
            if isinstance(function_call, dict) and "name" in function_call:
                tool_choice = {
                    "type": "function",
                    "function": {
                        "name": function_call["name"],
                    },
                }

        tool = None
        if (
            tool_choice is not None
            and isinstance(tool_choice, dict)
            and tools is not None
        ):
            name = tool_choice["function"]["name"]
            tool = next((t for t in tools if t["function"]["name"] == name), None)
            if tool is None:
                raise ValueError(f"Tool choice '{name}' not found in tools.")
            schema = tool["function"]["parameters"]
            try:
                grammar = llama_grammar.LlamaGrammar.from_json_schema(
                    json.dumps(schema), verbose=llama.verbose
                )
            except Exception as e:
                if llama.verbose:
                    print(str(e), file=sys.stderr)
                grammar = llama_grammar.LlamaGrammar.from_string(
                    llama_grammar.JSON_GBNF, verbose=llama.verbose
                )

        completion_or_chunks = llama.create_completion(
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            typical_p=typical_p,
            logprobs=top_logprobs if logprobs else None,
            stream=stream,
            stop=stop,
            seed=seed,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            repeat_penalty=repeat_penalty,
            tfs_z=tfs_z,
            mirostat_mode=mirostat_mode,
            mirostat_tau=mirostat_tau,
            mirostat_eta=mirostat_eta,
            model=model,
            logits_processor=logits_processor,
            grammar=grammar,
            logit_bias=logit_bias,
        )

        if tool is not None:
            tool_name = tool["function"]["name"]
            return _convert_completion_to_chat_function(
                tool_name, completion_or_chunks, stream
            )
        return _convert_completion_to_chat(completion_or_chunks, stream=stream)

    @staticmethod
    def _load_image(image_url: str) -> bytes:
        if image_url.startswith("data:"):
            import base64

            image_bytes = base64.b64decode(image_url.split(",")[1])
            return image_bytes
        else:
            import urllib.request

            with urllib.request.urlopen(image_url) as f:
                image_bytes = f.read()
                return image_bytes

    @staticmethod
    def get_image_urls(messages: list[llama_types.ChatCompletionRequestMessage]):
        image_urls: list[str] = []
        for message in messages:
            if message["role"] == "user":
                if message["content"] is None:
                    continue
                for content in message["content"]:
                    if isinstance(content, dict) and "type" in content:
                        if content["type"] == "image_url":
                            if (
                                isinstance(content["image_url"], dict)
                                and "url" in content["image_url"]
                            ):
                                image_urls.append(content["image_url"]["url"])
                            else:
                                image_urls.append(content["image_url"])
        return image_urls

    @staticmethod
    def get_audio_urls(messages: list[llama_types.ChatCompletionRequestMessage]):
        audio_urls: list[str] = []
        for message in messages:
            if message["role"] == "user":
                if message["content"] is None:
                    continue
                content = message["content"]
                # Handle string content (no audio) and list content
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and "type" in part:
                            if part["type"] == "audio_url":
                                if (
                                    isinstance(part["audio_url"], dict)
                                    and "url" in part["audio_url"]
                                ):
                                    audio_urls.append(part["audio_url"]["url"])
                                else:
                                    audio_urls.append(part["audio_url"])
        return audio_urls

    @classmethod
    def from_pretrained(
        cls,
        repo_id: str,
        filename: str | None,
        local_dir: str | os.PathLike[str] | None = None,
        local_dir_use_symlinks: bool | Literal["auto"] = "auto",
        cache_dir: str | os.PathLike[str] | None = None,
        **kwargs: Any,
    ) -> "MTMDChatHandler":
        import fnmatch
        from pathlib import Path

        try:
            from huggingface_hub import HfFileSystem, hf_hub_download  # type: ignore
            from huggingface_hub.utils import validate_repo_id  # type: ignore
        except ImportError:
            raise ImportError(
                "Llama.from_pretrained requires the huggingface-hub package. "
                "You can install it with `pip install huggingface-hub`."
            )

        validate_repo_id(repo_id)

        hffs = HfFileSystem()

        files = [
            file["name"] if isinstance(file, dict) else file
            for file in hffs.ls(repo_id)  # type: ignore
        ]

        file_list: list[str] = []
        for file in files:
            rel_path = Path(file).relative_to(repo_id)
            file_list.append(str(rel_path))

        matching_files = [file for file in file_list if fnmatch.fnmatch(file, filename)]  # type: ignore

        if len(matching_files) == 0:
            raise ValueError(
                f"No file found in {repo_id} that match {filename}\n\n"
                f"Available Files:\n{json.dumps(file_list)}"
            )

        if len(matching_files) > 1:
            raise ValueError(
                f"Multiple files found in {repo_id} matching {filename}\n\n"
                f"Available Files:\n{json.dumps(files)}"
            )

        (matching_file,) = matching_files

        subfolder = str(Path(matching_file).parent)
        filename = Path(matching_file).name

        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            subfolder=subfolder,
            local_dir=cast(Union[str, Path, None], local_dir),
            local_dir_use_symlinks=local_dir_use_symlinks,
            cache_dir=cast(Union[str, Path, None], cache_dir),
        )

        if local_dir is None:
            model_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                subfolder=subfolder,
                local_dir=local_dir,
                local_dir_use_symlinks=local_dir_use_symlinks,
                cache_dir=cast(Union[str, Path, None], cache_dir),
                local_files_only=True,
            )
        else:
            model_path = os.path.join(local_dir, filename)

        return cls(
            clip_model_path=model_path,
            **kwargs,
        )


class Gemma4ChatHandler(MTMDChatHandler):
    pass
