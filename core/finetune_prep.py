#!/usr/bin/env python3
"""
Fine-tuning data preparation for Codey-OS.

Exports interaction data for off-device fine-tuning using Unsloth + Colab.
Generates ShareGPT-style JSONL datasets and ready-to-run Colab notebooks.

This module handles:
- Dataset curation from episodic/long-term memory
- Quality filtering (successful interactions, user corrections)
- ShareGPT format export (messages with system/user/assistant roles)
- Unsloth Colab notebook generation
- User instructions for training workflow

Note: All heavy training happens off-device (Colab free tier T4 GPU).
Phone only does lightweight data export + file writing.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.state import get_state_store
from utils.logger import info, warning

# =============================================================================
# Dataset Curation
# =============================================================================


class DatasetCurator:
    """
    Curates high-quality fine-tuning examples from Codey-OS interaction history.

    Filters by:
    - Successful interactions (no errors, task completed)
    - User corrections accepted
    - Multi-turn conversations (richer context)
    - Recent interactions (more relevant to current style)
    """

    def __init__(self):
        self.state = get_state_store()

    def get_episodic_actions(self, days: int = 30, min_quality: float = 0.7) -> List[Dict]:
        """
        Retrieve episodic actions from the last N days.

        Args:
            days: Number of days to look back
            min_quality: Minimum quality score (0.0-1.0)

        Returns:
            List of action dictionaries
        """
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_ts = int(cutoff.timestamp())

        try:
            # Get episodic log from state
            actions_json = self.state.get("episodic_log")
            if not actions_json:
                return []

            actions = json.loads(actions_json)

            # Filter by date and quality
            filtered = []
            for action in actions:
                ts = action.get("timestamp", 0)
                if ts < cutoff_ts:
                    continue

                # Quality heuristics
                quality = self._calculate_quality(action)
                if quality >= min_quality:
                    action["_quality"] = quality
                    filtered.append(action)

            # Sort by quality descending
            filtered.sort(key=lambda x: x.get("_quality", 0), reverse=True)
            return filtered

        except Exception as e:
            warning(f"Failed to load episodic actions: {e}")
            return []

    def _calculate_quality(self, action: Dict) -> float:
        """
        Calculate quality score for an action.

        Heuristics:
        - Task completed successfully: +0.5
        - User accepted/corrected: +0.3
        - Multi-step task: +0.2
        - Recent (last 7 days): +0.1
        - Error occurred: -0.5
        """
        score = 0.5  # Base score

        # Success bonus
        if action.get("success", False):
            score += 0.3

        # Multi-step bonus
        if action.get("steps", 1) > 1:
            score += 0.2

        # Recency bonus
        ts = action.get("timestamp", 0)
        days_ago = (datetime.now().timestamp() - ts) / 86400
        if days_ago <= 7:
            score += 0.1

        # Error penalty
        if action.get("error"):
            score -= 0.5

        return max(0.0, min(1.0, score))

    def curate_verified(self, max_examples: int = 500, path=None) -> List[Dict]:
        """Examples from the trajectory store whose outcome an EXTERNAL verifier passed
        (pytest / bench grader / script exit code). This is the only trustworthy label
        source; the older `episodic_log` heuristic path never had data (NEW-546).
        Needs CODEY_TRAJECTORY=1 during use, then labeling via core.trajectory.label_*.

        WP0.5 (NEW-761): uses verified_training_episodes(), not the old
        bare verified_episodes() (removed) -- structurally excludes
        anything tagged by the frozen benchmark, so this export path
        cannot leak eval data into training even if a future caller
        forgets to filter it.

        WP1.2 (reconciled from codey-os-dev-v2's S0.1): episodes are now
        recorded at full fidelity (core/trajectory.py's _bounded/_budgeted),
        with truncation/oversize-omission happening only here, at export.
        A field ending in the LEGACY marker is pre-full-fidelity data from
        before this change landed; skipped outright rather than exported
        with a mid-field artifact baked in. Oversize-marked fields are
        exported as-is (text, not valid tool-call JSON) and caught later by
        export_hygiene.sanitize_examples's truncation-marker check."""
        from core.trajectory import LEGACY_TRUNC_MARKER, verified_training_episodes

        out = []
        legacy_skipped = 0
        for ep in verified_training_episodes(path=path, only_passed=True)[:max_examples]:
            # Legacy _trunc appended the marker at the END of a field; the same text
            # mid-field is legitimate content, so only an END match marks truncation.
            raw = [ep["prompt"], ep["final"]] + [x for c in ep["calls"] for x in (c[1], c[2])]
            if any(isinstance(x, str) and x.endswith(LEGACY_TRUNC_MARKER) for x in raw):
                legacy_skipped += 1
                continue
            convo = [
                {"role": "system", "content": "You are Codey, a local coding agent. Use tools via <tool>{json}</tool>."},
                {"role": "user", "content": ep["prompt"]},
            ]
            for name, args, result, _is_err in ep["calls"]:
                try:
                    a = json.loads(args)
                except Exception:
                    a = args  # legacy truncated / oversize args stored as text; excluded at export
                convo.append({"role": "assistant",
                              "content": "<tool>\n" + json.dumps({"name": name, "args": a}) + "\n</tool>"})
                convo.append({"role": "user", "content": "[Tool result]\n" + str(result)})
            if not ep["final"]:
                continue
            convo.append({"role": "assistant", "content": ep["final"]})
            out.append({"conversations": convo,
                        "metadata": {"source": "trajectory", "verifier": ep["verifier"],
                                     "verified": True, "episode_id": ep["id"]}})
        if legacy_skipped:
            info(f"curate_verified: skipped {legacy_skipped} episode(s) with legacy-truncated fields")
        return out

    def curate_examples(
        self, days: int = 30, min_quality: float = 0.7, max_examples: int = 500,
        verified_only: bool = False,
    ) -> List[Dict]:
        """
        Curate fine-tuning examples from history.

        Args:
            days: Days to look back
            min_quality: Minimum quality threshold
            max_examples: Maximum examples to return

        Returns:
            List of curated examples in ShareGPT format
        """
        examples = self.curate_verified(max_examples)
        if verified_only:
            return examples
        actions = self.get_episodic_actions(days, min_quality)

        for action in actions[: max(0, max_examples - len(examples))]:
            example = self._action_to_sharegpt(action)
            if example:
                example.setdefault("metadata", {})["verified"] = False  # heuristic label only
                examples.append(example)

        return examples

    def _action_to_sharegpt(self, action: Dict) -> Optional[Dict]:
        """
        Convert an episodic action to ShareGPT format with thought_trace.

        ShareGPT format (v3.0.0 — thought_trace):
        {
            "conversations": [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ],
            "thought_trace": {
                "observation": "raw user input",
                "symbolic_graph": {...},  // NetworkX adjacency list
                "utterances": {
                    "en": "English description",
                    "ar": "Arabic description",
                    "es": "Spanish description"
                }
            }
        }
        """
        user_msg = action.get("user_message", "")
        assistant_msg = action.get("response", "")

        if not user_msg or not assistant_msg:
            return None

        # Build system prompt from preferences
        system_prompt = self._build_system_prompt(action)

        # Build thought_trace for symbolic graph training
        thought_trace = self._build_thought_trace(action)

        result = {
            "conversations": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            "metadata": {
                "source": "codeyOS",
                "quality": action.get("_quality", 0.5),
                "timestamp": action.get("timestamp", 0),
                "tools_used": action.get("tools_used", []),
            },
        }

        # Attach thought_trace if available
        if thought_trace:
            result["thought_trace"] = thought_trace

        return result

    def _build_thought_trace(self, action: Dict) -> Optional[Dict]:
        """
        Build a thought_trace for the symbolic graph training objective.

        The thought_trace contains:
        - observation: raw user input
        - symbolic_graph: the graph state at the time of observation (subgraph)
        - utterances: parallel descriptions in multiple languages

        Training objective:
        - Given observation, predict symbolic_graph
        - Given symbolic_graph, predict utterances
        """
        user_msg = action.get("user_message", "")
        if not user_msg:
            return None

        try:
            from core.memory_v2 import memory as _mem

            # Get current graph state — this is the subgraph relevant to this observation
            # (concepts were added by the symbolic pipeline during this interaction)
            graph_state = _mem.get_graph_state()

            # Build utterances in multiple languages
            # The observation is the primary utterance; we attempt basic translations
            utterances = {"en": user_msg}

            # If the symbolic graph has concepts with multilingual utterances, include them
            for node in graph_state.get("nodes", []):
                node_utterances = node.get("utterances", {})
                for lang, text in node_utterances.items():
                    if lang != "en" and lang not in utterances:
                        utterances[lang] = text
                    elif lang == "en" and text != user_msg:
                        # Graph may have a normalized version of the observation
                        utterances["en"] = text

            return {
                "observation": user_msg,
                "symbolic_graph": graph_state,
                "utterances": utterances,
            }
        except Exception:
            return None

    def _build_system_prompt(self, action: Dict) -> str:
        """Build system prompt from learned preferences."""
        from core.learning import get_learning_manager

        learning = get_learning_manager()
        prefs = learning.get_all_preferences()

        parts = ["You are Codey-OS, a helpful AI coding assistant."]

        # Add learned preferences
        if prefs.get("test_framework"):
            parts.append(f"User prefers {prefs['test_framework']} for testing.")
        if prefs.get("code_style"):
            parts.append(f"User prefers {prefs['code_style']} code style.")
        if prefs.get("naming_convention"):
            parts.append(f"User prefers {prefs['naming_convention']} naming.")

        return " ".join(parts)


# =============================================================================
# Dataset Export
# =============================================================================


def export_dataset(
    examples: List[Dict], output_path: str, model_variant: str = "both"
) -> Tuple[str, int]:
    """
    Export examples to ShareGPT-style JSONL.

    Args:
        examples: List of ShareGPT examples
        output_path: Output directory
        model_variant: "4b" (deployed model), legacy "1.5b"/"7b", or "both"

    Returns:
        Tuple of (output_file, example_count)
    """
    # WP1.2 (export hygiene, from codey-os-dev-v2's S0.1): unconditional --
    # drops truncated/secret/duplicate examples BEFORE any file is created.
    # Scan errors propagate (fail closed); see core/export_hygiene.py.
    from core.export_hygiene import sanitize_examples

    examples, stats = sanitize_examples(examples)
    info(f"Export hygiene: {stats}")

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if model_variant == "both":
        # Export single combined file
        output_file = output_dir / "codey-finetune-combined.jsonl"
        count = _write_jsonl(examples, output_file)
        return str(output_file), count

    elif model_variant == "1.5b":
        # Filter for simpler examples (single-turn, style-focused)
        simple = [e for e in examples if len(e["conversations"]) <= 3]
        output_file = output_dir / "codey-finetune-1.5b.jsonl"
        count = _write_jsonl(simple, output_file)
        return str(output_file), count

    elif model_variant == "4b":
        # Deployed model (Qwen3.5-4B): keep full multi-step tool trajectories
        output_file = output_dir / "codey-finetune-4b.jsonl"
        count = _write_jsonl(examples, output_file)
        return str(output_file), count

    elif model_variant == "7b":
        # Include complex multi-turn examples
        output_file = output_dir / "codey-finetune-7b.jsonl"
        count = _write_jsonl(examples, output_file)
        return str(output_file), count

    else:
        raise ValueError(f"Unknown model variant: {model_variant}")


def _write_jsonl(examples: List[Dict], output_file: Path) -> int:
    """Write examples to JSONL file.

    WP1.2 (from codey-os-dev-v2's S0.1): write to a sibling temp file then
    atomically replace -- a failure mid-write must not leave a partial
    file nor destroy a previous export.
    """
    output_file = Path(output_file)
    count = 0
    tmp = None
    try:
        # unique name so concurrent exports cannot collide
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output_file.parent),
                                         prefix=output_file.name + ".", suffix=".tmp",
                                         delete=False) as f:
            tmp = f.name
            for example in examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
                count += 1
        os.replace(tmp, output_file)
    except BaseException:
        try:
            if tmp:
                os.unlink(tmp)
        except OSError:
            pass  # temp may never have been created; nothing to clean
        raise
    return count


# =============================================================================
# Colab Notebook Generation
# =============================================================================

UNSLOTH_NOTEBOOK_TEMPLATE = '''# Codey-OS Fine-tuning with Unsloth
# Model: {model_name}
# Generated: {generated_date}

"""
This notebook fine-tunes {model_name} on your Codey-OS interaction data.

Requirements:
- Google Colab free tier (T4 GPU, 16GB VRAM)
- Unsloth library (pre-installed in this notebook)
- Your exported JSONL dataset

Steps:
1. Upload your codey-finetune-*.jsonl file
2. Run all cells
3. Download the LoRA adapter
4. Import back to Codey-OS with: codeyOS --import-lora /path/to/adapter

Estimated time: 1-4 hours on free T4 GPU
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Install Unsloth (if not pre-installed)
# ─────────────────────────────────────────────────────────────────────────────
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps "xformers<0.0.27" trl peft accelerate bitsandbytes

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Load Your Dataset
# ─────────────────────────────────────────────────────────────────────────────
from google.colab import files
import json

print("Upload your codey-finetune-*.jsonl file:")
uploaded = files.upload()

# Read the uploaded file
jsonl_file = list(uploaded.keys())[0]
with open(jsonl_file, "r") as f:
    dataset = [json.loads(line) for line in f]

print(f"Loaded {{len(dataset)}} examples")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Load Base Model with Unsloth
# ─────────────────────────────────────────────────────────────────────────────
from unsloth import FastLanguageModel

# Model selection
{model_loading_code}

# Load model with 4-bit quantization (saves VRAM)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=model_id,
    max_seq_length=2048,
    load_in_4bit=True,  # 4-bit quantization
    fast_inference=True,  # Enable fast inference
)

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Configure LoRA Adapters
# ─────────────────────────────────────────────────────────────────────────────
model = FastLanguageModel.get_peft_model(
    model,
    r={lora_r},  # LoRA rank (16-32 recommended)
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_alpha={lora_alpha},
    lora_dropout=0,  # Optimized for performance
    bias="none",
)

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Prepare Training Data (Two-Step Symbolic Training)
# ─────────────────────────────────────────────────────────────────────────────
from trl import SFTTrainer
from transformers import TrainingArguments
import json

# Two-step training objective for symbolic graph reasoning:
#   Step A: observation -> symbolic_graph  (NL to structured representation)
#   Step B: symbolic_graph -> utterances   (structured to NL output)
def format_symbolic_training(example):
    \"\"\"Format thought_trace data for two-step symbolic training.\"\"\"
    conversations = example.get("conversations", [])
    thought_trace = example.get("thought_trace", None)

    if not thought_trace:
        # Fallback: standard conversation format
        text = ""
        for msg in conversations:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                text += f"User: {{content}}\\n\\n"
            elif role == "assistant":
                text += f"Assistant: {{content}}"
        return {{"text": text}}

    observation = thought_trace.get("observation", "")
    symbolic_graph = thought_trace.get("symbolic_graph", {{"nodes": [], "edges": []}})
    utterances = thought_trace.get("utterances", {{"en": observation}})

    # Format as two-step training:
    # Step A: observation -> symbolic_graph
    graph_json = json.dumps(symbolic_graph, ensure_ascii=False, indent=2)
    step_a = f"Convert this observation to a symbolic graph:\\n\\nObservation: {{observation}}\\n\\nSymbolic Graph: {{graph_json}}"

    # Step B: symbolic_graph -> utterances (in user's language)
    utt_json = json.dumps(utterances, ensure_ascii=False, indent=2)
    step_b = f"Given this symbolic graph, generate natural language descriptions:\\n\\nGraph: {{graph_json}}\\n\\nDescriptions: {{utt_json}}"

    # Combine both steps
    text = f"Step 1: {{step_a}}\\n\\nStep 2: {{step_b}}"
    return {{"text": text}}

# Apply formatting — prioritize thought_trace when available
has_thought_trace = any(ex.get("thought_trace") for ex in dataset)
if has_thought_trace:
    formatted_dataset = [format_symbolic_training(ex) for ex in dataset]
    print("Using two-step symbolic training format (observation -> graph -> utterances)")
else:
    # Fallback to standard conversation format
    def format_conversation(example):
        conversations = example["conversations"]
        text = ""
        for msg in conversations:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                text += f"User: {{content}}\\n\\n"
            elif role == "assistant":
                text += f"Assistant: {{content}}"
        return {{"text": text}}
    formatted_dataset = [format_conversation(ex) for ex in dataset]
    print("Using standard conversation format (no thought_trace found)")

# Training arguments
training_args = TrainingArguments(
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    warmup_steps=5,
    max_steps={max_steps},  # Adjust based on dataset size
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    output_dir="outputs",
    optim="adamw_8bit",
    seed=42,
)

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Train!
# ─────────────────────────────────────────────────────────────────────────────
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=formatted_dataset,
    dataset_text_field="text",
    max_seq_length=2048,
    args=training_args,
)

print("Starting training...")
trainer.train()

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Save and Download Adapter
# ─────────────────────────────────────────────────────────────────────────────
# Save the LoRA adapter
adapter_path = "codey-lora-adapter"
model.save_pretrained(adapter_path)
tokenizer.save_pretrained(adapter_path)

# Create a zip file for download
import shutil
shutil.make_archive("codey-lora-adapter", "zip", adapter_path)

# Download
files.download("codey-lora-adapter.zip")

print("""
─────────────────────────────────────────────────────────────────
✓ Training complete!

Next steps:
1. Download the codey-lora-adapter.zip file
2. Extract it on your device
3. Import to Codey-OS: codeyOS --import-lora /path/to/codey-lora-adapter

To merge with base model (optional):
  python merge_adapter.py --base {model_id} --adapter codey-lora-adapter --output merged-model
─────────────────────────────────────────────────────────────────
""")
'''


NB4B_CELLS = [
("markdown", "# Codey-OS fine-tune: Qwen3.5-4B (16-bit LoRA)\n\n"
 "Matches the model Codey-OS actually runs (Qwen3.5-4B). Source: Unsloth Qwen3.5 fine-tuning guide "
 "(https://unsloth.ai/docs/models/qwen3.5/fine-tune): use 16-bit LoRA, **not** 4-bit QLoRA "
 "(not recommended for Qwen3.5), `transformers` v5 required, about 10GB VRAM (fits a free T4).\n\n"
 "**UNVERIFIED on Colab as of generation ({generated_date}).** If a cell errors, fix it there and tell Codey-OS "
 "maintainers; do not assume success. Kernel compile on T4 can be slow.\n"),
("code", "!pip install --upgrade unsloth unsloth_zoo\n"
 "!pip install --upgrade \"transformers>=5\" trl peft accelerate datasets torchvision pillow\n"),
("code", "import json\nfrom google.colab import files\n"
 "print('Upload your codey-finetune-4b.jsonl (verified trajectories only):')\n"
 "up = files.upload()\nrows = [json.loads(l) for l in open(list(up)[0]) if l.strip()]\n"
 "assert rows, 'empty dataset'\nprint(len(rows), 'examples')\n"
 "print('verified fraction:', sum(bool(r.get('metadata', {{}}).get('verified')) for r in rows) / len(rows))\n"),
("code", "from unsloth import FastLanguageModel\n"
 "model, tokenizer = FastLanguageModel.from_pretrained(\n"
 "    model_name='{model_id}', max_seq_length=4096, load_in_16bit=True, full_finetuning=False)\n"
 "model = FastLanguageModel.get_peft_model(\n"
 "    model, r={lora_r}, lora_alpha={lora_alpha}, lora_dropout=0, bias='none',\n"
 "    # CONCERN: Qwen3.5 mixes linear-attention and full-attention layers; these standard names come from\n"
 "    # Unsloth's generic recipe and were NOT checked against this model's module list. Print\n"
 "    # [n for n,_ in model.named_modules()] if training reports no trainable params.\n"
 "    target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'])\n"),
("code", "from datasets import Dataset\n"
 "def to_text(r):\n"
 "    return {{'text': tokenizer.apply_chat_template(r['conversations'], tokenize=False)}}\n"
 "ds = Dataset.from_list(rows).map(to_text)\n"
 "split = ds.train_test_split(test_size=0.1, seed=42) if len(ds) >= 20 else {{'train': ds, 'test': None}}\n"
 "print(split['train'][0]['text'][:800])\n"),
("code", "from trl import SFTTrainer, SFTConfig\nfrom unsloth import is_bfloat16_supported\n"
 "trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=split['train'], eval_dataset=split['test'],\n"
 "    args=SFTConfig(dataset_text_field='text', max_seq_length=4096, per_device_train_batch_size=1,\n"
 "        gradient_accumulation_steps=8, warmup_steps=5, max_steps={max_steps}, learning_rate=1e-4,\n"
 "        bf16=is_bfloat16_supported(), fp16=not is_bfloat16_supported(), logging_steps=5,\n"
 "        optim='adamw_8bit', output_dir='outputs', seed=42, report_to='none'))\ntrainer.train()\n"),
("code", "import shutil\nmodel.save_pretrained('codey-lora-adapter'); tokenizer.save_pretrained('codey-lora-adapter')\n"
 "shutil.make_archive('codey-lora-adapter', 'zip', 'codey-lora-adapter')\nfiles.download('codey-lora-adapter.zip')\n"
 "print('Do NOT adopt this adapter because training loss fell. Adopt it only if bench shows a gate-approved gain '\n"
 "      '(python -m bench.promote). See AGI_AUDIT_PLAN.md.')\n"),
]


def _cell(kind: str, text: str) -> dict:
    src = text.splitlines(keepends=True)  # Jupyter requires line endings inside each source string
    if kind == "markdown":
        return {"cell_type": "markdown", "metadata": {}, "source": src}
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src}


def generate_notebook(
    model_variant: str,
    output_path: str,
    lora_r: int = 16,
    lora_alpha: int = 16,
    max_steps: int = 200,
) -> str:
    """
    Generate Unsloth Colab notebook for fine-tuning.

    Args:
        model_variant: "1.5b" or "7b"
        output_path: Output directory
        lora_r: LoRA rank
        lora_alpha: LoRA alpha
        max_steps: Maximum training steps

    Returns:
        Path to generated notebook
    """
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Model configuration
    v2_cells = None
    if model_variant == "4b":
        model_name = "Qwen3.5-4B"
        model_id = "Qwen/Qwen3.5-4B"
        notebook_name = "codey-finetune-qwen3.5-4b.ipynb"
        v2_cells = NB4B_CELLS
    elif model_variant == "1.5b":
        model_name = "Qwen2.5-1.5B-Instruct"
        model_id = "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit"
        notebook_name = "codey-finetune-qwen-coder-1.5b.ipynb"
    elif model_variant == "7b":
        model_name = "Qwen2.5-Coder-7B-Instruct"
        model_id = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"
        notebook_name = "codey-finetune-qwen-coder-7b.ipynb"
    else:
        raise ValueError(f"Unknown model variant: {model_variant}")

    if v2_cells is not None:
        fmt = dict(model_id=model_id, lora_r=lora_r, lora_alpha=lora_alpha, max_steps=max_steps,
                   generated_date=datetime.now().strftime("%Y-%m-%d"))
        notebook = {
            "cells": [_cell(k, t.format(**fmt)) for k, t in v2_cells],
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}},
            "nbformat": 4,
            "nbformat_minor": 4,
        }
        output_file = output_dir / notebook_name
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=2)
        info(f"Generated notebook: {output_file}")
        return str(output_file)

    # Legacy (Qwen2.5) variants: NOT the deployed model. Kept for compatibility.
    notebook_content = UNSLOTH_NOTEBOOK_TEMPLATE.format(
        model_name=model_name,
        model_id=model_id,
        model_loading_code=f'model_id = "{model_id}"',
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        max_steps=max_steps,
        generated_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # Convert to Jupyter notebook format
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"# {model_name} Fine-tuning with Unsloth\n\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": notebook_content.splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    output_file = output_dir / notebook_name
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=2)

    info(f"Generated notebook: {output_file}")
    return str(output_file)


# =============================================================================
# User Instructions
# =============================================================================


def print_instructions(dataset_path: str, notebook_path: str, model_variant: str):
    """Print step-by-step instructions for the user."""

    instructions = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Codey-OS Fine-tuning Workflow                             ║
╠══════════════════════════════════════════════════════════════════════════════╣

✓ Dataset exported: {dataset_path}
✓ Notebook generated: {notebook_path}

────────────────────────────────────────────────────────────────────────────────
STEP 1: Open Google Colab
────────────────────────────────────────────────────────────────────────────────
  1. Go to https://colab.research.google.com
  2. Click "Upload notebook"
  3. Upload: {notebook_path}

────────────────────────────────────────────────────────────────────────────────
STEP 2: Upload Dataset
────────────────────────────────────────────────────────────────────────────────
  1. Run the first cell in the notebook
  2. When prompted, upload: {dataset_path}
  3. Wait for dataset to load

────────────────────────────────────────────────────────────────────────────────
STEP 3: Train
────────────────────────────────────────────────────────────────────────────────
  1. Click "Runtime" → "Run all"
  2. Training will take 1-4 hours (free T4 GPU)
  3. Do NOT close the browser tab

────────────────────────────────────────────────────────────────────────────────
STEP 4: Download Adapter
────────────────────────────────────────────────────────────────────────────────
  1. After training completes, the adapter will auto-download
  2. File: codey-lora-adapter.zip
  3. Transfer to your Android device

────────────────────────────────────────────────────────────────────────────────
STEP 5: Import to Codey-OS
────────────────────────────────────────────────────────────────────────────────
  On your device:
  
  1. Extract the zip file:
     unzip codey-lora-adapter.zip
  
  2. Import the adapter:
     codeyOS --import-lora /path/to/codey-lora-adapter --lora-merge
  
  3. Test the fine-tuned model:
     codeyOS "test the new model"

────────────────────────────────────────────────────────────────────────────────
TROUBLESHOOTING
────────────────────────────────────────────────────────────────────────────────
• Out of memory: Reduce batch_size to 1 in notebook
• Training too slow: reduce max_steps or max_seq_length in the notebook
• Poor results: Increase max_steps or lower min_quality threshold
• Import fails: Ensure adapter folder contains adapter_config.json

────────────────────────────────────────────────────────────────────────────────
NOTES
────────────────────────────────────────────────────────────────────────────────
• Free Colab T4 GPU: 16GB VRAM, ~12 hour session limit
• 4b = the deployed Qwen3.5-4B (16-bit LoRA, ~10GB VRAM). 1.5b/7b are legacy Qwen2.5 variants Codey-OS does not run.
• BEFORE adopting an adapter: run bench for base vs tuned and require an approving
  `python -m bench.promote` decision. Lower training loss is not evidence of improvement.
• UNVERIFIED: llama.cpp LoRA conversion for Qwen3.5 has not been tested here (see LIVE_TEST_QUEUE.md)
• LoRA adapter size: ~100-500MB (much smaller than full model)

╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(instructions)


# =============================================================================
# Main Entry Point
# =============================================================================


def prepare_finetune_data(
    days: int = 30, min_quality: float = 0.7, model_variant: str = "4b", output_dir: str = None
) -> Dict[str, str]:
    """
    Main entry point for fine-tuning data preparation.

    Args:
        days: Days of history to include
        min_quality: Minimum quality threshold
        model_variant: "4b" (default, deployed model), legacy "1.5b"/"7b", or "both"
        output_dir: Output directory (default: ~/Downloads)

    Returns:
        Dict with paths to generated files
    """
    if output_dir is None:
        output_dir = str(Path.home() / "Downloads" / "codey-finetune")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    info(f"Curating examples from last {days} days (min_quality={min_quality})...")

    # Curate examples
    curator = DatasetCurator()
    examples = curator.curate_examples(days, min_quality)

    if not examples:
        warning("No high-quality examples found. Try lowering min_quality or increasing days.")
        return {"error": "No examples found"}

    info(f"Curated {len(examples)} examples")

    # Export dataset(s)
    results = {}

    if model_variant == "both":
        # Export combined + both variants
        for variant in ["1.5b", "7b"]:
            path, count = export_dataset(examples, str(output_path), variant)
            results[f"dataset_{variant}"] = path
            info(f"Exported {count} examples to {path}")

            # Generate notebook
            nb_path = generate_notebook(variant, str(output_path))
            results[f"notebook_{variant}"] = nb_path
    else:
        path, count = export_dataset(examples, str(output_path), model_variant)
        results["dataset"] = path
        info(f"Exported {count} examples to {path}")

        nb_path = generate_notebook(model_variant, str(output_path))
        results["notebook"] = nb_path

    # Print instructions
    variant_key = f"dataset_{model_variant}" if model_variant == "both" else "dataset"
    nb_key = f"notebook_{model_variant}" if model_variant == "both" else "notebook"

    if model_variant == "both":
        print_instructions(results["dataset_1.5b"], results["notebook_1.5b"], "1.5b")
        print_instructions(results["dataset_7b"], results["notebook_7b"], "7b")
    else:
        print_instructions(results[variant_key], results[nb_key], model_variant)

    return results
