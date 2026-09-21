# syntax=docker/dockerfile:1.7
# ACE-Step 1.5 — image RunPod serverless AVEC LES MODELES DEDANS.
#
# Pourquoi les modeles sont dans l'image, et pas sur un volume reseau : un network volume RunPod est
# facture 0,07 $/Go/mois **meme quand rien ne tourne**. La feuille de route du projet impose
# « serverless, rien a vide » — donc l'image porte ses ~9,5 Go de poids, et le compte ne paie
# strictement rien entre deux morceaux.
#
# Elle se construit sur GitHub Actions (rien a installer sur le PC) et se publie sur ghcr.io.
#
# Base Ubuntu 24.04 (python 3.12 d'origine), comme l'installation sur pod deja eprouvee le 20/09 :
# 22.04 n'a pas python 3.11 dans ses depots, et 24.04 impose --break-system-packages (PEP 668).

ARG CUDA_VERSION=12.8.1
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev git curl ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# ⚠ Sur Ubuntu 24.04, pip appartient a Debian : `pip install -U pip` echoue avec
# « Cannot uninstall pip 24.0, RECORD file not found » (paye sur le run 35512337345), et PEP 668
# refuse toute installation hors venv. Un environnement virtuel regle les deux d'un coup.
RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app

# --- ACE-Step, epingle a une reference (image reproductible ; « main » derive avec le temps) -------
# 21/09 : FIGE sur le commit que le PC fait tourner (installation editable de
# C:/Users/quang/Documents/ACEStep/ace, arbre propre). « main » derive : le cloud doit rendre ce
# que le PC rend, sinon un morceau fait en ligne sonne autrement qu'un morceau fait en local.
ARG ACESTEP_REF=ca1e85fe9430179831e6bc6be790c332190a3866
RUN git clone https://github.com/ace-step/ACE-Step-1.5 /app/ace \
    && git -C /app/ace checkout ${ACESTEP_REF} \
    && git -C /app/ace rev-parse HEAD > /app/ACESTEP_COMMIT

# --- torch cu128, puis le paquet ------------------------------------------------------------------
# ⚠ ICI ON EST SOUS LINUX : ace-step y epingle **torch 2.10.0+cu128 / torchvision 0.25.0**. Les
# versions 2.7.1 / 0.22.1 sont celles de l'installation WINDOWS de Quang — les transposer ici casse
# le build (« No matching distribution found for torch==2.10.0+cu128 », run 35512690359). Le piege
# etait deja ecrit dans acestep_pod_install.sh, point 3.
# `vector_quantize_pytorch` est OBLIGATOIRE — sans lui le modele REFUSE de charger (paye le 20/09).
# ⚠ `nano-vllm` N'EST PAS SUR PyPI — il est VENDU dans le depot (`acestep/third_parts/nano-vllm`),
# et `pip install -e .` echoue sans lui (run 35512495380). En local on s'en passe parce que Windows
# ne sait pas le construire ; ici on est sous Linux, donc on l'installe depuis le depot, comme le
# fait deja le script d'installation sur pod. Le moteur reste sur ACESTEP_LM_BACKEND=pt.
# torchao / torchcodec en --no-deps, sinon ils tirent un AUTRE torch et cassent tout.
RUN pip install -U pip setuptools wheel \
    && pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 \
         --index-url https://download.pytorch.org/whl/cu128 \
    && pip install /app/ace/acestep/third_parts/nano-vllm \
    && pip install -e /app/ace \
    && pip install vector_quantize_pytorch diskcache lightning lycoris-lora modelscope \
         "peft>=0.18.0" "python-multipart>=0.0.18" pytorch-wavelets pywavelets \
         tensorboard toml typer-slim \
    && pip install --no-deps "torchao>=0.16.0,<0.17.0" "torchcodec>=0.9.1" \
    && pip install runpod huggingface_hub hf_transfer \
    && rm -rf /root/.cache/pip

# --- LES POIDS, dans l'image (c'est tout l'interet) ---------------------------------------------
# ⚠ LE MODELE EST `acestep-v15-turbo` depuis le 21/09 (il etait `base` le 20/09).
# Pourquoi : le pod du 20/09 au matin, celui des essais que Quang a valides a l'oreille, ne chargeait
# QUE turbo — et le moteur retombe EN SILENCE sur son modele primaire quand le `model` demande n'est
# pas charge (`acestep/api/job_model_selection.py`). « Valide = base » avait ete deduit du PAYLOAD,
# jamais d'un log. Banc du 21/09 (meme son, 3 rejeux) : turbo -4,5/-4,7/-4,6 points, REGULIER ;
# base +0,6/-7,0/-19,8, ERRATIQUE. Avec base ici, le renfort en ligne rendait l'ancien son (Umbrella,
# 21/09 06:08, -10,6 points).
# Source et revision FIGEES : ce sont exactement les poids du PC. Empreintes SHA-256 comparees le
# 21/09 (model.safetensors turbo 3f6e0797…, VAE da17edb6…, silence_latent a778e9dd…) : identiques.
# Le build ECHOUE si l'empreinte du modele differe (sha256sum -c) : jamais d'image au mauvais modele.
ARG HF_REVISION=19671f406d603126926c1b7e2adc169acbcade22
ENV HF_HUB_ENABLE_HF_TRANSFER=1
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('ACE-Step/Ace-Step1.5', revision='${HF_REVISION}', local_dir='/app/checkpoints', allow_patterns=['acestep-v15-turbo/*','acestep-5Hz-lm-1.7B/*','vae/*','Qwen3-Embedding-0.6B/*','config.json'])" \
    && echo "3f6e0797fad420a39bd33979eb6e840e30989e34a3794e843d23b60ec6e422d7  /app/checkpoints/acestep-v15-turbo/model.safetensors" | sha256sum -c - \
    && du -sh /app/checkpoints

# ⚠ `ACESTEP_CHECKPOINTS_DIR` EST OBLIGATOIRE. Sans elle, le moteur resout ses poids dans
# `<project_root>/checkpoints` = `/app/ace/checkpoints`, qui est VIDE — il tente alors de les
# TELECHARGER, ce que `HF_HUB_OFFLINE=1` interdit, et la generation echoue apres ~190 s sans dire
# pourquoi (paye le 20/09, 0,034 $). En local ca passait parce que les chemins absolus de Windows
# masquaient le probleme. Sources lues : `acestep/model_downloader.py:get_checkpoints_dir` et
# `init_service_orchestrator.py` (`model_path = os.path.join(checkpoint_dir, config_path)`).
ENV ACESTEP_CHECKPOINTS_DIR=/app/checkpoints \
    ACESTEP_CONFIG_PATH=acestep-v15-turbo \
    ACESTEP_LM_MODEL_PATH=/app/checkpoints/acestep-5Hz-lm-1.7B \
    ACESTEP_LM_BACKEND=pt \
    ACESTEP_DEVICE=cuda \
    HF_HUB_OFFLINE=1

COPY handler.py /app/handler.py
CMD ["python", "-u", "/app/handler.py"]
