"""LLM layer: offline TinyLlama primary, optional silent remote fallback."""
import json
import re
import threading

import config

_lock = threading.Lock()
_tok = None
_model = None
_torch = None
_device = "cpu"
_gemini_ready = False


def _load_local():
    """Lazy-load TinyLlama. Returns True on success."""
    global _tok, _model, _torch, _device
    if _model is not None:
        return True
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        _torch = torch
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _tok = AutoTokenizer.from_pretrained(config.MODEL_NAME)
        _model = AutoModelForCausalLM.from_pretrained(
            config.MODEL_NAME,
            torch_dtype=torch.float16 if _device == "cuda" else torch.float32,
        ).to(_device)
        _model.eval()
        print(f"[llm] TinyLlama loaded on {_device}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[llm] local load failed: {e}")
        return False


def _gen_local(system, prompt, max_new_tokens, temperature):
    if not _load_local():
        raise RuntimeError("local model unavailable")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": prompt}]
    try:
        text = _tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:  # noqa: BLE001
        text = f"<|system|>\n{system}</s>\n<|user|>\n{prompt}</s>\n<|assistant|>\n"
    inputs = _tok(text, return_tensors="pt").to(_device)
    with _torch.no_grad():
        out = _model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 0.01),
            top_p=0.9,
            repetition_penalty=1.15,
            pad_token_id=_tok.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    return _tok.decode(gen, skip_special_tokens=True).strip()


def _gen_gemini(system, prompt, max_new_tokens, temperature):
    global _gemini_ready
    if not config.GEMINI_API_KEY:
        raise RuntimeError("no remote key")
    import google.generativeai as genai
    if not _gemini_ready:
        genai.configure(api_key=config.GEMINI_API_KEY)
        _gemini_ready = True
    last = None
    for name in config.GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(name, system_instruction=system)
            resp = model.generate_content(
                prompt,
                generation_config={"temperature": temperature,
                                   "max_output_tokens": max_new_tokens},
            )
            return (resp.text or "").strip()
        except Exception as e:  # noqa: BLE001
            last = e
            continue
    raise RuntimeError(f"remote failed: {last}")


def generate(prompt, system="You are a helpful legal assistant.",
             max_new_tokens=None, temperature=None):
    """Generate text. Honours config.LLM_BACKEND with silent fallback."""
    max_new_tokens = max_new_tokens or config.MAX_NEW_TOKENS
    temperature = config.GEN_TEMPERATURE if temperature is None else temperature
    backend = config.LLM_BACKEND
    with _lock:
        if backend == "gemini":
            return _gen_gemini(system, prompt, max_new_tokens, temperature)
        try:
            return _gen_local(system, prompt, max_new_tokens, temperature)
        except Exception as e:  # noqa: BLE001
            if backend == "local":
                raise
            print(f"[llm] falling back to remote: {e}")
            return _gen_gemini(system, prompt, max_new_tokens, temperature)


def generate_json(prompt, system, max_new_tokens=None, temperature=0.1):
    """Generate and best-effort parse a JSON object/array from the output."""
    raw = generate(prompt, system=system, max_new_tokens=max_new_tokens, temperature=temperature)
    return _extract_json(raw)


def _extract_json(raw):
    if not raw:
        return None
    # strip code fences
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    # find first balanced {...} or [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == opener:
                depth += 1
            elif raw[i] == closer:
                depth -= 1
                if depth == 0:
                    chunk = raw[start:i + 1]
                    try:
                        return json.loads(chunk)
                    except Exception:  # noqa: BLE001
                        break
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def status():
    return {
        "local_loaded": _model is not None,
        "device": _device,
        "backend": config.LLM_BACKEND,
        "remote_available": bool(config.GEMINI_API_KEY),
    }
