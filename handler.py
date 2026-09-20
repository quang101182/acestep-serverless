# -*- coding: utf-8 -*-
"""Worker RunPod serverless — enrichissement ACE-Step (`task_type="lego"`).

Il fait exactement ce que fait le PC en local, par le MEME chemin (le serveur HTTP d'ACE-Step lance
dans le conteneur, puis /release_task + /query_result). C'est volontaire : ce chemin est deja
eprouve, plutot que d'appeler des fonctions internes dont l'interface peut changer d'une version a
l'autre.

Entree  : {"audio_b64": <mp3 base64>, "lyrics": str, "prompt": str, "duration": float}
Sortie  : {"ok": true, "audio_b64": <mp3 base64>, "secondes": float, "commit": str}

⚠ Les gros fichiers ne passent PAS par le payload RunPod (limite de quelques Mo a l'aller, ~20 Mo au
retour) : le PC envoie du MP3 192 kbit/s et recoit du MP3 320 kbit/s. Aucun stockage tiers, et
surtout AUCUN secret ne voyage — le worker n'a pas besoin de joindre le PC.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import runpod

PORT = int(os.environ.get("ACESTEP_API_PORT", "8901"))
BASE = "http://127.0.0.1:%d" % PORT
_SRV = {"proc": None}


def _get(path, timeout=5):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def _post(path, body, timeout=60):
    rq = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def demarre_serveur():
    """Le serveur vit pour TOUTE la duree du worker : un seul demarrage a froid, puis les morceaux
    suivants n'en paient rien. Il charge son modele a la PREMIERE requete, pas au demarrage — donc
    /health qui repond ne prouve pas qu'il est pret a travailler."""
    if _SRV["proc"] and _SRV["proc"].poll() is None:
        return
    env = dict(os.environ)
    env["ACESTEP_API_PORT"] = str(PORT)
    _SRV["proc"] = subprocess.Popen([sys.executable, "-m", "acestep.api_server"],
                                    cwd="/app/ace", env=env,
                                    stdout=sys.stderr, stderr=subprocess.STDOUT)
    for _ in range(180):
        time.sleep(1)
        if _get("/health", timeout=3) is not None:
            print("[worker] serveur ACE-Step pret", flush=True)
            return
    raise RuntimeError("le serveur ACE-Step n'a pas repondu en 180 s")


def en_mp3(src, dst, debit="320k"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-b:a", debit, dst], check=True)


def handler(job):
    t0 = time.time()
    e = job.get("input") or {}
    if e.get("ping"):
        # Reveil a blanc ET DIAGNOSTIC. ⚠ Le 20/09, un enrichissement en ligne a mis **20 min** la ou
        # le PC met 3 min 25 — et il etait impossible de savoir si le worker calculait seulement sur
        # GPU. On ne redeploie plus une image sans pouvoir repondre a cette question en 10 secondes.
        diag = {}
        try:
            import torch
            diag = {"torch": torch.__version__, "cuda_dispo": bool(torch.cuda.is_available()),
                    "cuda_version": getattr(torch.version, "cuda", None),
                    "gpu": (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),
                    "vram_go": (round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)
                                if torch.cuda.is_available() else None)}
        except Exception as ex:
            diag = {"erreur_torch": str(ex)[:200]}
        if not e.get("diag_seul"):
            demarre_serveur()
        return {"ok": True, "pong": True, "secondes": round(time.time() - t0, 1), **diag}

    # --- CREATION PURE (mode 🎨 « moteur 2 seul »), ajoute le 20/09 au soir ---------------------
    # ACE-Step sait COMPOSER, pas seulement enrichir : `task_type="text2music"`, donc SANS
    # `src_audio_path`. Champs valides sur pod le 20/09 par `_musique-wip/acestep_inversion.py`
    # (piste B, « que des nombres ») : lyrics, prompt, audio_duration, vocal_language, batch_size,
    # + bpm / key_scale / time_signature / thinking.
    #
    # ⚠ POURQUOI ON LE VALIDE ICI ET PAS SUR LE PC : `text2music` passe par le LM (contrairement a
    # `lego`, qui l'ignore — « Skipping LM for task_type='lego' »), donc il demande plus de memoire.
    # La carte du PC avait 8,1 Go pris par les applis de Quang : le garde-fou anti-gel aurait refuse
    # le depart, et le forcer risquait de geler sa machine. Ici la carte fait 48 Go et ne coute rien
    # a vide. Le cloud sert de banc d'essai SANS RISQUE, c'est son deuxieme usage.
    if e.get("creer"):
        duree = float(e.get("duration") or 0)
        if duree <= 0:
            return {"ok": False, "erreur": "il faut une duration pour creer"}
        corps = {"task_type": "text2music", "lyrics": e.get("lyrics") or "",
                 "prompt": e.get("prompt") or "", "audio_duration": duree,
                 "vocal_language": e.get("vocal_language") or "english",
                 "batch_size": 1}
        for opt in ("bpm", "key_scale", "time_signature", "thinking"):
            if e.get(opt) is not None:
                corps[opt] = e[opt]
        return _travaille(corps, e, t0)

    b64 = e.get("audio_b64")
    duree = float(e.get("duration") or 0)
    if not b64 or duree <= 0:
        return {"ok": False, "erreur": "il faut audio_b64 et duration"}

    demarre_serveur()
    tmp = tempfile.gettempdir()
    src = os.path.join(tmp, "src_%d.mp3" % int(time.time()))
    with open(src, "wb") as f:
        f.write(base64.b64decode(b64))

    corps = {"task_type": "lego", "src_audio_path": src,
             "lyrics": e.get("lyrics") or "", "prompt": e.get("prompt") or "",
             "global_caption": e.get("prompt") or "", "audio_duration": duree, "batch_size": 1}
    return _travaille(corps, e, t0, a_effacer=[src])


def _travaille(corps, e, t0, a_effacer=()):
    """Soumet une tache au moteur et attend son resultat — le MEME chemin pour l'enrichissement et
    pour la creation. C'est volontaire : ce chemin (release_task -> query_result -> extraction du
    fichier -> MP3) est deja eprouve en production ; un second chemin parallele serait un second
    endroit ou se tromper. Seul le `corps` change."""
    demarre_serveur()
    rep = _post("/release_task", corps, timeout=120)
    tid = ((rep or {}).get("data") or {}).get("task_id")
    if not tid:
        return {"ok": False, "erreur": "le moteur a refuse la tache : %s" % str(rep)[:300]}

    fichier, statut = None, 0
    limite = float(e.get("timeout") or 1800)
    while time.time() - t0 < limite:
        time.sleep(4)
        q = _post("/query_result", {"task_id_list": [tid]}, timeout=60)
        items = (q or {}).get("data") or []
        if not items:
            continue
        statut = items[0].get("status")
        if statut == 1:
            try:
                res = json.loads(items[0].get("result") or "[]")
                ch = (res[0] or {}).get("file") or ""
                import re
                from urllib.parse import unquote
                m = re.search(r"path=([^&]+)", ch)
                fichier = unquote(m.group(1)) if m else None
            except Exception as ex:
                return {"ok": False, "erreur": "reponse illisible : %s" % str(ex)[:200]}
            break
        if statut == 2:
            # ⚠ Ne JAMAIS se contenter de « le moteur a echoue » : sans la raison, on diagnostique a
            # l'aveugle depuis le PC (paye le 20/09 — un travail de 189 s pour un message vide).
            detail = ""
            try:
                detail = json.dumps(json.loads(items[0].get("result") or "[]"), ensure_ascii=False)[:900]
            except Exception:
                detail = str(items[0].get("result"))[:900]
            return {"ok": False, "erreur": "le moteur a echoue", "detail": detail,
                    "progres": (items[0].get("progress_text") or "")[:400]}

    if not fichier or not os.path.isfile(fichier):
        return {"ok": False, "erreur": "aucun fichier rendu (statut %s)" % statut,
                "detail": str((items[0] if items else {}).get("result"))[:900]}

    out = os.path.join(tempfile.gettempdir(), "out_%d.mp3" % int(time.time()))
    try:
        en_mp3(fichier, out, e.get("debit") or "320k")
    except Exception as ex:
        return {"ok": False, "erreur": "conversion MP3 impossible : %s" % str(ex)[:200]}
    with open(out, "rb") as f:
        sortie = base64.b64encode(f.read()).decode("ascii")
    for p in list(a_effacer) + [out, fichier]:
        try:
            os.remove(p)
        except OSError:
            pass
    commit = ""
    try:
        with open("/app/ACESTEP_COMMIT") as f:
            commit = f.read().strip()[:12]
    except Exception:
        pass
    return {"ok": True, "audio_b64": sortie, "secondes": round(time.time() - t0, 1),
            "octets": len(sortie), "commit": commit}


runpod.serverless.start({"handler": handler})
