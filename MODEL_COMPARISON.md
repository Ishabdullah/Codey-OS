# Codey-OS Model Selection Guide

## Samsung Galaxy S24 Ultra Hardware Constraints

| Specification | Value |
|--------------|-------|
| Processor | Snapdragon 8 Gen 3 |
| RAM | 12 GB |
| Available for models | ~8-9 GB (OS + apps need ~3-4 GB) |
| Max comfortable model size | ~7B parameters (Q4 quantization) |
| Max aggressive quantization | ~14B parameters (Q3/Q2 quantization) |
| Context window practical limit | 32K tokens (128K possible but slow) |

---

## Current Model Configuration (Upgraded)

| Role | Model | Size | Quantization | RAM Usage | Context |
|------|-------|------|--------------|-----------|---------|
| Coder | Qwen2.5-Coder-7B-Instruct | 7.6B | Q4_K_M | ~4.2 GB | 128K |
| Planner | **Qwen2.5-Coder-1.5B-Instruct** | 1.5B | Q4_K_M | ~1 GB | 32K |
| Embedder | nomic-embed-text-v1.5 | 137M | Q4 | ~80 MB | 8K |

**Total RAM usage:** ~5.3 GB

---

## Top Open-Source Models for Local Coding (June 2026)

### Tier 1: Best for S24 Ultra (7B and under)

#### 1. Qwen2.5-Coder-7B-Instruct (Current Choice)
- **Parameters:** 7.6B
- **Quantized Size (Q4_K_M):** ~4.2 GB
- **Context:** 128K tokens
- **License:** Apache 2.0
- **HumanEval:** ~83% (SOTA for 7B class)
- **MBPP:** ~75%
- **Strengths:** Best-in-class coding for its size, excellent instruction following, 128K context
- **Weaknesses:** Slightly slower than smaller models
- **Verdict:** **Recommended to keep** — best 7B coding model available

#### 2. Qwen2.5-Coder-3B-Instruct
- **Parameters:** 3B
- **Quantized Size (Q4_K_M):** ~1.8 GB
- **Context:** 32K tokens
- **License:** Apache 2.0
- **HumanEval:** ~72%
- **MBPP:** ~65%
- **Strengths:** Fast inference, good for mobile, solid coding ability
- **Weaknesses:** Lower quality than 7B for complex tasks
- **Verdict:** Good alternative if speed is prioritized over quality

#### 3. Qwen2.5-Coder-1.5B-Instruct
- **Parameters:** 1.5B
- **Quantized Size (Q4_K_M):** ~1 GB
- **Context:** 32K tokens
- **License:** Apache 2.0
- **HumanEval:** ~60%
- **Strengths:** Very fast, minimal RAM, good for simple tasks
- **Weaknesses:** Limited reasoning capability
- **Verdict:** Potential planner upgrade (currently using 0.5B)

#### 4. Google Gemma-2-2B-IT
- **Parameters:** 2B
- **Quantized Size (Q4_K_M):** ~1.3 GB
- **Context:** 8K tokens
- **License:** Gemma (permissive, some restrictions)
- **HumanEval:** ~35% (not code-specific)
- **Strengths:** Excellent general reasoning, Google quality training
- **Weaknesses:** Not code-specialized, short context
- **Verdict:** Not recommended for coding — general purpose only

#### 5. Phi-3-mini-4k-instruct
- **Parameters:** 3.8B
- **Quantized Size (Q4_K_M):** ~2.2 GB
- **Context:** 4K tokens (128K with long context variant)
- **License:** MIT
- **HumanEval:** ~58%
- **Strengths:** Excellent reasoning for size, Microsoft quality
- **Weaknesses:** Short default context, not code-specialized
- **Verdict:** Good general model, not optimal for coding

#### 6. StarCoder2-3B
- **Parameters:** 3B
- **Quantized Size (Q4_K_M):** ~1.8 GB
- **Context:** 16K tokens
- **License:** BigCode OpenRAIL-M
- **HumanEval:** ~32% (base), ~55% (instruct)
- **Strengths:** Code-focused, good multilingual support
- **Weaknesses:** Older architecture, lower quality than Qwen
- **Verdict:** Outdated — Qwen2.5-Coder is superior

### Tier 2: Possible with Aggressive Quantization (14B)

#### 7. Qwen2.5-Coder-14B-Instruct
- **Parameters:** 14B
- **Quantized Size (Q3_K_M):** ~5.5 GB
- **Context:** 128K tokens
- **License:** Apache 2.0
- **HumanEval:** ~88%
- **MBPP:** ~80%
- **Strengths:** Near-GPT-4 coding ability, excellent reasoning
- **Weaknesses:** Slow on mobile, requires aggressive quantization
- **Verdict:** **Best upgrade option** if willing to accept speed trade-off

#### 8. DeepSeek-Coder-V2-Lite-Instruct
- **Parameters:** 16B total, 2.4B active (MoE)
- **Quantized Size (Q4_K_M):** ~9 GB
- **Context:** 128K tokens
- **License:** DeepSeek (commercial use allowed)
- **HumanEval:** ~90% (but requires full precision for MoE)
- **Strengths:** MoE efficiency, excellent coding
- **Weaknesses:** Full model too large for mobile, MoE needs special handling
- **Verdict:** **Not recommended** — MoE architecture doesn't quantize well for mobile

#### 9. Gemma-2-9B-IT
- **Parameters:** 9B
- **Quantized Size (Q4_K_M):** ~5.5 GB
- **Context:** 8K tokens
- **License:** Gemma
- **HumanEval:** ~40%
- **Strengths:** Good general model, Google quality
- **Weaknesses:** Not code-specialized, short context
- **Verdict:** Not recommended for coding tasks

### Tier 3: Desktop Only (27B+)

#### 10. Qwen2.5-Coder-32B-Instruct
- **Parameters:** 32B
- **Quantized Size (Q4_K_M):** ~18 GB
- **Context:** 128K tokens
- **HumanEval:** ~92% (SOTA open-source)
- **Verdict:** **Too large for mobile** — desktop/server only

#### 11. DeepSeek-Coder-V2-236B
- **Parameters:** 236B total, 21B active
- **Verdict:** **Way too large for mobile**

---

## Benchmark Comparison (HumanEval pass@1)

| Model | Size | HumanEval | Context | Mobile Viable |
|-------|------|-----------|---------|---------------|
| Qwen2.5-Coder-32B | 32B | ~92% | 128K | No |
| DeepSeek-Coder-V2-Lite | 16B (2.4B active) | ~90% | 128K | No (MoE) |
| Qwen2.5-Coder-14B | 14B | ~88% | 128K | Aggressive Q3 |
| **Qwen2.5-Coder-7B** | **7B** | **~83%** | **128K** | **Yes (Q4)** |
| Qwen2.5-Coder-3B | 3B | ~72% | 32K | Yes |
| Qwen2.5-Coder-1.5B | 1.5B | ~60% | 32K | Yes |
| Phi-3-mini | 3.8B | ~58% | 4K/128K | Yes |
| Gemma-2-9B | 9B | ~40% | 8K | Possible (slow) |
| StarCoder2-3B | 3B | ~55% | 16K | Yes |

---

## Recommendations for Codey-OS

### Option A: Keep Current Setup (Recommended)

| Role | Model | Why |
|------|-------|-----|
| Coder | Qwen2.5-Coder-7B Q4_K_M | Best coding quality at this size |
| Planner | Qwen2.5-0.5B Q8_0 | Fast, efficient for planning |
| Embedder | nomic-embed-text-v1.5 | Optimal for RAG |

**Pros:** Proven, stable, best quality-to-size ratio
**Cons:** No improvement in coding quality

### Option B: Upgrade Planner (Low Risk)

| Role | Model | Change |
|------|-------|--------|
| Coder | Qwen2.5-Coder-7B Q4_K_M | Same |
| Planner | **Qwen2.5-Coder-1.5B Q4_K_M** | Upgrade from 0.5B |
| Embedder | nomic-embed-text-v1.5 | Same |

**Pros:** Better planning with code-specific model, ~1GB more RAM
**Cons:** Slightly slower planning

**Impact:** 
- Planning accuracy improvement: ~15-20%
- Task decomposition quality: Significant improvement
- RAM increase: ~500MB additional

### Option C: Max Quality (High Risk/Reward)

| Role | Model | Change |
|------|-------|--------|
| Coder | **Qwen2.5-Coder-14B Q3_K_M** | Upgrade from 7B |
| Planner | Qwen2.5-0.5B Q8_0 | Same |
| Embedder | nomic-embed-text-v1.5 | Same |

**Pros:** Near-GPT-4 coding ability
**Cons:** 
- Requires aggressive quantization (quality loss)
- 2-3x slower inference
- May cause thermal throttling
- Uses ~6GB RAM total (tight on 12GB device)

**Impact:**
- HumanEval: 83% → 88%
- Better complex reasoning
- Slower response times (10-30s → 20-60s)

### Option D: Google Gemma Integration (Experimental)

| Role | Model | Change |
|------|-------|--------|
| Coder | Qwen2.5-Coder-7B Q4_K_M | Same |
| Planner | **Gemma-2-2B-IT Q4_K_M** | Replace 0.5B |
| Embedder | nomic-embed-text-v1.5 | Same |

**Pros:** Better general reasoning for planning
**Cons:**
- Gemma not code-specialized
- Shorter context (8K vs 32K)
- License restrictions

**Verdict:** Not recommended — Qwen2.5-Coder-1.5B is better for code planning

---

## Why Qwen2.5-Coder Remains the Best Choice

### 1. Code-Specific Training
- Trained on 5.5 trillion tokens including source code
- Optimized for code generation, completion, and explanation
- Supports 92+ programming languages

### 2. Context Window
- 128K context (vs 8K for Gemma, 16K for StarCoder)
- Critical for large file editing and multi-file context

### 3. Instruction Following
- Excellent at following complex instructions
- Good at structured output (JSON tool calls)

### 4. Quantization Quality
- Q4_K_M quantization preserves quality well
- Minimal degradation from FP16

### 5. Ecosystem Support
- Full llama.cpp support
- Active community and updates
- Apache 2.0 license (no restrictions)

---

## Future Considerations

### When to Upgrade
1. **Qwen3 release** — Expected improvements in reasoning
2. **Better quantization** — Q5/Q6 variants for mobile
3. **More RAM devices** — Future phones with 16GB+ RAM
4. **MoE for mobile** — When MoE quantization improves

### Model Hot-Swapping
Consider implementing model switching based on task:
- Simple edits → Qwen2.5-Coder-3B (fast)
- Complex refactoring → Qwen2.5-Coder-7B (quality)
- Planning → Qwen2.5-Coder-1.5B (fast + code-aware)

---

## Conclusion

**For S24 Ultra with 12GB RAM:**

1. **Keep Qwen2.5-Coder-7B** as the coder — it's the best option
2. **Consider upgrading planner to Qwen2.5-Coder-1.5B** for better code-aware planning
3. **Avoid Gemma for coding** — not code-specialized
4. **Avoid 14B models** — too slow for mobile UX
5. **Wait for Qwen3** — expected significant improvements

**The current setup is already optimal for the hardware constraints.**
