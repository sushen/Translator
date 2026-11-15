import gc
import re
from typing import List, Optional
import torch
from app.translation.translator import BaseTranslator
from app.translation.model_manager import ModelManager
from app.translation.translation_validator import TranslationValidator
from app.document.paragraph_model import ParagraphModel
from app.utils.logging import get_logger

logger = get_logger(__name__)

TARGET_LANG_CODE = "ben_Beng"
SOURCE_LANG_CODE = "eng_Latn"

class LocalTranslator(BaseTranslator):
    """
    Offline Local AI Translator using Meta NLLB-200 open-source translation model.
    Runs completely on local machine without external API calls or keys.
    """
    def __init__(
        self,
        model_manager: Optional[ModelManager] = None,
        preferred_device: str = "auto",
        batch_size: int = 8,
        max_length: int = 512
    ):
        self.model_manager = model_manager or ModelManager()
        self.preferred_device = preferred_device
        self.batch_size = batch_size
        self.max_length = max_length

    def _get_model_and_tokenizer(self):
        return self.model_manager.load_model(preferred_device=self.preferred_device)

    def _split_text(self, text, tokenizer):
        """Keep every source character while respecting the tokenizer's input limit."""
        chunks = []
        remaining = text
        while remaining:
            if len(tokenizer.encode(remaining, add_special_tokens=True)) <= self.max_length:
                chunks.append(remaining)
                break
            low, high = 0, len(remaining)
            while low < high:
                mid = (low + high + 1) // 2
                if len(tokenizer.encode(remaining[:mid], add_special_tokens=True)) <= self.max_length:
                    low = mid
                else:
                    high = mid - 1
            if low == 0:
                raise ValueError("Input token budget is too small for one source character")
            # Prefer a sentence or word boundary near the end of the fitting prefix.
            prefix = remaining[:low]
            boundaries = list(re.finditer(r'(?<=[.!?;])\s+|\s+', prefix))
            candidates = [m.end() for m in boundaries if m.end() >= low // 2]
            cut = candidates[-1] if candidates else low
            chunks.append(remaining[:cut])
            remaining = remaining[cut:]
        return chunks

    def _translate_text_list(self, texts: List[str]) -> List[str]:
        if not texts:
            return []

        tokenizer, model, device = self._get_model_and_tokenizer()

        # Target language BOS token ID for NLLB-200
        if hasattr(tokenizer, "lang_code_to_id") and TARGET_LANG_CODE in tokenizer.lang_code_to_id:
            forced_bos_id = tokenizer.lang_code_to_id[TARGET_LANG_CODE]
        else:
            forced_bos_id = tokenizer.convert_tokens_to_ids(TARGET_LANG_CODE)

        chunks_by_text = [self._split_text(t, tokenizer) if t.strip() else [] for t in texts]
        flat_texts = [chunk for chunks in chunks_by_text for chunk in chunks]
        results = []
        for i in range(0, len(flat_texts), self.batch_size):
            sub_texts = flat_texts[i:i + self.batch_size]

            # Pre-clean empty/whitespace texts
            cleaned_indices = [idx for idx, t in enumerate(sub_texts) if t and t.strip()]
            if not cleaned_indices:
                results.extend([""] * len(sub_texts))
                continue

            sub_batch_texts = [sub_texts[idx] for idx in cleaned_indices]

            try:
                inputs = tokenizer(
                    sub_batch_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=False
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}

                with torch.no_grad():
                    generated_tokens = model.generate(
                        **inputs,
                        forced_bos_token_id=forced_bos_id,
                        max_new_tokens=self.max_length,
                        num_beams=2,
                        early_stopping=True
                    )

                decoded = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
                if len(decoded) != len(sub_batch_texts):
                    raise RuntimeError("Model returned an incomplete translation batch")
                if isinstance(generated_tokens, torch.Tensor):
                    eos = model.generation_config.eos_token_id
                    eos_ids = eos if isinstance(eos, list) else [eos]
                    pad = model.generation_config.pad_token_id
                    for index, row in enumerate(generated_tokens.tolist()):
                        if pad not in eos_ids:
                            while row and row[-1] == pad:
                                row.pop()
                        if len(row) >= self.max_length + 1 or (eos is not None and (not row or row[-1] not in eos_ids)):
                            decoded[index] = "[Translation Failed: output reached generation limit]"

                sub_res = [""] * len(sub_texts)
                for clean_idx, dec_text in zip(cleaned_indices, decoded):
                    sub_res[clean_idx] = dec_text.strip()

                results.extend(sub_res)

            except torch.cuda.OutOfMemoryError as e:
                if device == "cpu":
                    raise RuntimeError("Insufficient memory for local translation on CPU") from e
                logger.error(f"CUDA Out Of Memory error during translation: {e}. Falling back to CPU.")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()

                # Fallback model manager device to CPU and retry
                self.preferred_device = "cpu"
                self.model_manager.unload_model()
                return self._translate_text_list(texts)

            except Exception as e:
                logger.error(f"Error during local model translation batch execution: {e}")
                # Fall back to returning placeholders or error indicators
                sub_res = [f"[Translation Failed: {t}]" if t.strip() else "" for t in sub_texts]
                results.extend(sub_res)

        joined = []
        offset = 0
        for chunks in chunks_by_text:
            translated_chunks = results[offset:offset + len(chunks)]
            offset += len(chunks)
            if any(t.startswith("[Translation Failed:") or not t.strip() for t in translated_chunks):
                joined.append("[Translation Failed: one or more source chunks failed]")
            else:
                joined.append(" ".join(translated_chunks))
        return joined

    def translate_paragraph(self, text: str, is_heading: bool = False) -> str:
        if not text or not text.strip():
            return ""

        translations = self._translate_text_list([text])
        res_text = translations[0] if translations else ""

        valid, msg = TranslationValidator.validate(text, res_text)
        if not valid:
            logger.warning(f"Local translation validation issue: {msg}")

        return res_text

    def translate_batch(self, paragraphs: List[ParagraphModel]) -> List[str]:
        if not paragraphs:
            return []

        raw_texts = [p.text for p in paragraphs]
        translated_texts = self._translate_text_list(raw_texts)

        validated_results = []
        for p, res_text in zip(paragraphs, translated_texts):
            valid, msg = TranslationValidator.validate(p.text, res_text)
            if valid or not res_text.startswith("[Translation Failed"):
                validated_results.append(res_text)
            else:
                validated_results.append(res_text)

        return validated_results

    def unload(self):
        """Clean up local model resources."""
        self.model_manager.unload_model()
