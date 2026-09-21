> ## ▶️ REPRISE — lundi 21/09/2026, 10 h 10
> **Le document à lire en premier : `C:/Users/quang/Documents/ComfyUI/ROADMAP-lisibilite-playlist.md`**
> (autosuffisant : état exact en v7.11, conception validée par Quang, ce qui reste à faire dans l'ordre,
> pièges payés, bancs). Prochaine étape : **zone C de la ligne de playlist en cases fixes** (§ 3.1).
> ⚠️ Deux décisions à demander à Quang : le **cloud tourne encore sur le modèle `base`** (§ 3.2) et le
> **mode 🎨 + reprise jette la partition** (§ 3.3).

> ## ✅ ÉTAT au 21/09/2026 11 h 45 — le cloud tourne en TURBO, validé en réel
> Image **`:11`** (commit `a3ce38e`) : `acestep-v15-turbo`, poids HF figés `19671f40` (empreintes
> identiques au PC, vérifiées au build), code ACE-Step figé `ca1e85fe` (= le PC). Template pointé sur le
> tag **numéroté** `:11`. Le worker renvoie le modèle réellement chargé (`/v1/models`) ; le PC refuse
> tout son qui ne vient pas de turbo. Banc réel `test_v695_cloud_reel.py` **10/10** : 126 s, **0,037 $**,
> extinction 62 s. ⚠️ Toute la prose ci-dessous qui dit « modèle `base` » décrit l'état du 20/09.

# Reprise — brancher le moteur 2 (ACE-Step) en cloud pour Generate Studio

> Dossier **autosuffisant** : tout ce qu'il faut est ici, aucun renvoi à une mémoire externe.
> Écrit le 20/09/2026 au soir, après une session qui a **mal mené** ce chantier. Lis la méthode
> avant de coder : elle est la raison d'être de ce fichier.

---

## 1. Ce qu'il faut obtenir

Quand la carte graphique du PC est prise (Quang joue), un morceau déjà composé par le moteur 1 (YuE2)
doit partir **en ligne** pour y être enrichi par ACE-Step (`task_type="lego"`), puis revenir.
**Décision de Quang, 20/09 : la bascule est AUTOMATIQUE** — on ne lui demande rien, un voyant dit
seulement où ça a calculé. Objectif réel : **ne pas ralentir son jeu**, pas aller plus vite.

⛔ **Sa condition, répétée deux fois** : *« tu feras bien attention que le RunPod ne consomme pas
d'argent silencieusement par heure »*. Précédent réel : un pod oublié une nuit = **38 $** en juin.

---

## 2. ⚠️ LA MÉTHODE — c'est ici que la session du 20/09 s'est plantée

Elle a **construit une image de 9,4 Go pour découvrir** si le conteneur marchait. Chaque erreur,
même triviale, coûtait **11 min de build + 5 à 13 min pour tirer l'image + jusqu'à 20 min de test**.
Payé **quatre fois**, pour des causes toutes connues d'avance.

**Fais l'inverse :**

1. **Un pod jetable interactif d'abord** — GPU **A40 48 Go** (`NVIDIA A40`, ~0,35 $/h), image
   `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`. Installe avec la recette **déjà éprouvée** :
   `C:/Users/quang/Documents/ComfyUI/_musique-wip/acestep_pod_install.sh` (elle documente ses pièges).
2. **Fais tourner un VRAI enrichissement dessus** et **chronomètre-le**. Tant que ça n'a pas tourné
   une fois, rien n'est acquis.
3. **Seulement ensuite**, fige cette recette exacte dans l'image serverless de ce dépôt.
4. **Termine le pod** dès que c'est fait, et **vérifie le compte** (§ 6).

📌 Règle générale : si ton cycle essai → correction dépasse **10 minutes**, tu es dans le mauvais
environnement. Arrête-toi et déplace la boucle.

---

## 2-bis. ✅ ÇA MARCHE — validé en réel le 20/09 au soir (21 h)

**Deux enrichissements en ligne ont abouti**, son modifié, original conservé, coût au journal,
extinction constatée en **63 s**. Le § 3 ci-dessous décrit l'état d'AVANT cette validation ; il est
conservé pour l'historique, mais **« aucun enrichissement n'a jamais abouti » est désormais FAUX**.

### Les DEUX causes du blocage — elles se cumulaient, d'où l'impasse

1. **Aucune machine disponible.** Les 7 pools d'origine (H100/A100/A40/A6000) sont les plus demandés
   du marché : deux travaux sont restés **20 min** et **11 min** en file sans jamais démarrer. La
   carte qui a finalement répondu n'était **pas dans la liste d'origine**.
2. **Disque conteneur trop petit.** ⚠ **L'image ne fait PAS 9,4 Go : elle fait 14,90 Go compressée**
   (une seule couche de 7,88 Go), donc bien plus posée. Avec `containerDiskInGb: 40` l'image se
   téléchargeait **jusqu'au bout** puis le conteneur ne pouvait pas démarrer. **Porté à 100 Go.**

⛔ **Le piège qui rend ce blocage invisible** : RunPod affiche **« worker is ready » APRÈS le
téléchargement mais AVANT le lancement du conteneur**, et `/health` rend `ready: 1, idle: 1`. Tout
paraît sain pendant que la file ne bouge pas. Ne jamais conclure d'un `ready` que le code tourne.

### 🔑 Lire les logs du worker SANS le tableau de bord — c'est ce qui a tranché

```bash
curl -sL -o runpodctl.exe https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-windows-amd64.exe
./runpodctl.exe config --apiKey "$(cat .runpod_token_write)"
./runpodctl.exe serverless logs <endpoint> [--follow]    # JSON lines {source,line,ts,workerId}
./runpodctl.exe serverless health <endpoint>
./runpodctl.exe gpu list                                 # tarifs + stock réel par datacenter
```

**La lecture qui diagnostique** : compter les lignes par `source`. **100 lignes `system`, 0 ligne
`container`** = le conteneur sort avant que le handler démarre. Le CLI documente lui-même ce cas.
(L'API REST et GraphQL n'exposent **aucun** log — seul ce CLI le fait.)

### 💸 LE DÉFAUT LE PLUS GRAVE, et il venait du correctif lui-même

Élargir les pools a fait prendre une carte à **3,49 $/h**, alors que `ACE_CLOUD_TARIF_H` valait
**0,69**. Un morceau annoncé **0,0711 $** au journal en a coûté **0,4236 $** — **facteur 6**, et le
plafond de 5 $/mois aurait sauté cinq fois avant que l'app ne le sache.

- ✅ **Pools restreints aux 48 Go bon marché** : A40 **0,49** · RTX 6000 Ada **0,84** · L40 ·
  L40S **1,09 $/h**. (Pour mémoire : RTX PRO 6000 2,09 · H100 SXM **3,49**.)
- ✅ `ACE_CLOUD_TARIF_H = 1.20` — un **MAJORANT du pool**, jamais une moyenne.
- ⛔ **Toute réouverture des pools à une carte plus chère DOIT remonter ce nombre dans le même
  geste**, sinon le garde-fou re-ment en silence.

### ⚠ Le veilleur d'argent annonçait 0 $ à tort

`depense_mois()` ne lisait que le journal du proxy, **écrit uniquement quand l'app bascule d'elle-même** :
tout essai lancé à la main lui était invisible. Il affichait « 0,0000 $ » pendant que RunPod avait
facturé **0,6469 $**. Corrigé : il lit `GET https://rest.runpod.io/v1/billing/endpoints?bucketSize=month`
et retient **le plus grand des deux** ; si RunPod ne répond pas il le dit, au lieu d'un zéro rassurant.
⚠ Cette API exige un **User-Agent de navigateur** (sinon Cloudflare rend `error code: 1010`).

### ⏱ Les temps et les coûts MESURÉS (morceau de 92,9 s)

| Situation | Temps | Coût facturé |
|---|---|---|
| Machine **chaude** | **191 s** (×2,06 du temps réel) | 0,0342 $ *(tarif 0,69 supposé)* |
| Machine **froide** (démarrage compris) | **379 s** (×4,08) | **0,4236 $ réels** |
| Ping de diagnostic seul (démarrage à froid) | 307 s | 0,00003 $ |
| *Rappel local, RTX 5070 Ti carte libre* | *205 s* | *0 $* |

⇒ **Le cloud n'est PAS plus rapide que le PC** : à chaud c'est équivalent. Son seul intérêt est de
**laisser la carte libre pendant que Quang joue**. Ne jamais le vendre comme un gain de vitesse.

### Autres pièges payés ce soir-là

- **Un service relit son fichier au DÉMARRAGE** : le proxy tournait depuis 16 h 37 avec l'ancien
  tarif alors que le fichier était corrigé à 19 h 19. Vérifier `CreationDate` du process contre
  `LastWriteTime` du fichier. `launch-generate-agent.ps1` est **idempotent** : il ne relance PAS un
  proxy déjà vivant — il faut le tuer d'abord.
- **Le banc criait au loup** : il contrôlait l'extinction **20 s** après la fin, alors qu'elle prend
  60 s (`idleTimeout`) + propagation. Corrigé : il patiente jusqu'à 240 s en relisant toutes les 10 s.
- `workersStandby: 1` **n'est PAS un réglage** de facturation (l'API refuse de l'écrire) : valeur
  calculée. Ne pas crier à la fuite d'argent en le voyant.
- **Forcer le recyclage d'un worker** (pour qu'il reprenne une nouvelle config) : `workersMax: 0`,
  attendre ~30 s, puis `workersMax: 1`. Un worker déjà lancé **garde son ancienne configuration**.
- Un ping vaut **0,00003 $** : `python _musique-wip/acestep_cloud_ping.py` (diagnostic seul) répond
  torch / CUDA / nom du GPU / VRAM. À jouer **avant** tout diagnostic compliqué.
- Un travail **`IN_QUEUE` ne se facture pas** — d'où « ça n'a rien coûté » malgré 31 min d'attente.

---

## 3. L'état exact au 20/09 au soir

**Côté PC — LIVRÉ, TESTÉ, EN SERVICE** (app `generate_studio.html` en **v6.95**) :
- le moteur 2 tourne **en local** : `enrich_loop` dans `_studio_llm_proxy.py`, marqueur
  `enrichissement.json` par morceau, son d'origine gardé dans `gs/audio/_bruts/<morceau>.flac` ;
- écran des 4 modes (🎵 Moteur 1 · ✨ **1 + 2 par défaut** · 🎨 Moteur 2 · ⚖️ 1 et 2) ;
- pastilles ① / ② / ①+② dans la playlist, ☁️ déjà câblé pour le cloud ;
- le lecteur attend l'enrichissement (sinon il joue un son remplacé sous lui).
- Modèle servi : **`acestep-v15-base`** — celui que Quang a validé à l'oreille. Pas turbo.
- Mesures locales (RTX 5070 Ti 16 Go), morceau de 93 s : **205 s** avec `base` carte encombrée,
  129 s avec `turbo`. Le moteur monte à **7,4 Go de pointe** ; sous ~8 Go libres il tombe en mode
  contraint (jusqu'à 5× plus lent) — c'est **ce seuil qui déclenche la bascule cloud**
  (`ACE_VRAM_CONFORT = 8000`).

**Côté cloud — EN PLACE MAIS JAMAIS VALIDÉ** :
- image publique `ghcr.io/quang101182/acestep-serverless:latest` (9,4 Go, modèle `base`), construite
  par GitHub Actions depuis ce dépôt ;
- endpoint RunPod **`8pk1uqelel51rl`** (`acestep-moteur2`), `workersMin: 0`, `workersMax: 1`,
  `idleTimeout: 60`, pools `ADA_80_PRO,AMPERE_80,AMPERE_48` ;
- son identifiant est dans `C:/Users/quang/Documents/ComfyUI/.acestep_endpoint` — **ce fichier seul
  autorise le proxy à basculer en ligne** ; le supprimer désactive tout le cloud proprement.
- ⛔ **Aucun enrichissement en ligne n'a jamais abouti.** C'est tout le travail qui reste.

---

## 4. Les pièges déjà payés — ne les repaie pas

**Construction de l'image**
1. ❌ **`easimon/maximize-build-space`** : un runner `ubuntu-latest` a déjà **87 Go libres** ;
   l'action réserve cet espace ailleurs et ne laisse que 8 Go à Docker → « no space left ». Elle
   **cause** la panne qu'elle prétend éviter.
2. Ubuntu 24.04 : `pip install -U pip` échoue (pip appartient à Debian) → **installer dans un venv**.
3. **`nano-vllm` n'est pas sur PyPI** : il est vendu dans le dépôt
   (`acestep/third_parts/nano-vllm`) ; `pip install -e .` échoue sans lui.
4. ⚠️ **torch n'a pas la même version selon l'OS** : Windows **2.7.1 / 0.22.1**,
   Linux **2.10.0+cu128 / 0.25.0**. Transposer les versions Windows casse le build.
5. ⚠️ **`ACESTEP_CHECKPOINTS_DIR` est obligatoire** : sans elle, le moteur cherche ses poids dans
   `<projet>/checkpoints` (vide), tente de les **retélécharger** — interdit par `HF_HUB_OFFLINE=1` —
   et échoue après ~190 s **sans message**. (`acestep/model_downloader.py:get_checkpoints_dir`.)

**API RunPod**
6. ⛔ **`/runsync` est INUTILISABLE pour un travail long** : l'identifiant `sync-…` qu'il rend est
   refusé par `/status/<id>` **et** `/cancel/<id>` (404). Le travail devient insuivable **et
   inarrêtable** — c'est ce qui a provoqué les deux fuites. **Utiliser `/run`.**
7. ⛔ **Abandonner côté client n'arrête RIEN** : il faut `POST /v2/<ep>/cancel/<id>`. Déjà corrigé
   dans `enrich_cloud` (`_ace_cloud_annule`, sur tous les chemins de sortie).
8. La clé **en lecture seule** passe `/health` (200) mais rend **403 sur `/run`** — utiliser
   `.runpod_token_write`. Les deux clés se comportant pareil sur `/health`, le piège est invisible.
9. Modifier l'endpoint rend **`409 Conflict`** pendant ~1 min sur les lancements suivants.
10. **24 Go ne suffisent pas** : sur `AMPERE_24`, un morceau de 93 s n'était **pas fini après
    20 min**. La roadmap disait déjà `lego` **« testé sur A40 48 Go »**. Le pool **80 Go** est resté
    **13 min en file** sans démarrer (capacité indisponible ce soir-là) → **A40 48 Go est le bon
    point de départ**.
11. Le payload est limité : **MP3 192 kbit/s** à l'aller (le plus long morceau = 7,8 Mo en base64,
    pour une limite de 10 Mo). `enrich_cloud` redescend le débit et **renonce** plutôt que d'envoyer
    un appel voué à l'échec.
12. Un banc **ne doit pas attendre la réponse HTTP** d'un travail de 15-20 min : il expirait et
    **nettoyait le dossier sous un travail en cours**. Suivre le **marqueur sur le disque**.
13. Le banc créait un **doublon facturé** : la boucle `enrich_loop` prenait le même dossier. Il pose
    maintenant le mode sur « moteur 1 seul » le temps de l'essai.

---

## 5. Ce qui reste à faire, dans l'ordre

1. **Pod jetable A40** → installer → **un enrichissement réel qui aboutit** → noter le temps.
2. Reporter la recette exacte dans le `Dockerfile` de ce dépôt, rebuild, **ping de diagnostic**
   (`{"input":{"ping":true,"diag_seul":true}}` rend torch / CUDA / nom du GPU / VRAM).
3. `python _musique-wip/test_v695_cloud_reel.py` doit passer **9/9**.
4. Choisir le GPU **le moins cher qui tient la performance** (payer 2 $/h pendant 3 min coûte moins
   que 0,69 $/h pendant 25).
5. Vérifier le **voyant ☁️** dans la playlist sur un morceau réellement fait en ligne.
6. Finir la feuille de route : **filtres cumulables par moteur** + barre orange (maquette § 5 de
   `C:/Users/quang/Documents/ComfyUI/GENERATE_STUDIO_MAQUETTE_MOTEURS_v0.3.html`).

---

## 6. Sécurité argent — à vérifier À CHAQUE FOIS

```bash
python C:/Users/quang/Documents/ComfyUI/acestep_veille_cloud.py     # 0 = rien ne coûte
```
Il est aussi planifié tous les jours à 9h50 (tâche Windows `MoteurDeuxVeilleCloud`).

- **Geste d'urgence** si un worker s'emballe : `saveEndpoint` avec **`workersMax: 0`** → 0 $/h en
  moins de 15 s (constaté deux fois).
- **Purger la file** : `POST /v2/<ep>/purge-queue`.
- Plafond en dur côté proxy : **5 $/mois** (`ACE_CLOUD_PLAFOND_MOIS`) — au-delà, plus de bascule.
- État au 20/09 au soir : **0 pod, 0 volume, 0 $/h, crédit 33,07 $** ; essais de la journée **0,64 $**.
- ⭐ **Aucune carte bancaire enregistrée** sur le compte RunPod → la perte maximale possible est le
  crédit prépayé. **Ne jamais en réenregistrer une** sans que Quang le décide.
- ⚠️ **Pas de network volume** : il serait facturé 0,07 $/Go/mois **même à l'arrêt**. C'est la raison
  d'être de l'image auto-portante.

---

## 7. Ce qu'il ne faut PAS refaire

- ⛔ Ne pas re-présenter le cloud comme « plus rapide » ou « 0,02 $ le morceau » : mesuré,
  c'est **0,69 $/h** en serverless 24 Go et **4 à 13 min de démarrage à froid**.
- ⛔ Ne pas reposer à Quang la question « volume réseau ou image ? » : **tranché — image, rien à vide**.
- ⛔ Ne pas toucher aux images ni à la vidéo : les images ne quittent **jamais** le PC, la vidéo n'a
  **jamais** de bascule automatique (0,54 $ les 6 s contre ~0,10 $ un morceau).
