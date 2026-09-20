# acestep-serverless — le moteur 2 de Generate Studio, à la demande

Image RunPod **serverless** qui enrichit un morceau déjà composé (ACE-Step 1.5, `task_type="lego"`).
Elle sert de renfort à Generate Studio quand la carte graphique du PC est prise par un jeu.

## Le parti pris : les modèles sont DANS l'image

Un *network volume* RunPod est facturé **0,07 $/Go/mois même quand rien ne tourne**. La règle du
projet est « serverless, rien à vide » — alors l'image porte ses ~9,5 Go de poids, et le compte ne
paie **strictement rien** entre deux morceaux. On paie la seconde de calcul, et c'est tout.

Contrepartie assumée : un démarrage à froid plus long (le temps que RunPod tire l'image), et une
image à reconstruire pour changer de modèle.

## Ce qu'elle reçoit, ce qu'elle rend

```jsonc
// entrée
{"audio_b64": "<mp3 192 kbit/s en base64>", "lyrics": "...", "prompt": "<style>", "duration": 242.1}
// sortie
{"ok": true, "audio_b64": "<mp3 320 kbit/s en base64>", "secondes": 131.4, "commit": "a1b2c3d4e5f6"}
```

`{"ping": true}` réveille le worker sans rien calculer — utile pour mesurer un démarrage à froid.

⚠️ **Les fichiers passent par le payload, pas par un stockage tiers** : c'est plus simple, et surtout
**aucun secret ne voyage** (le worker n'a jamais besoin de joindre le PC). En contrepartie il faut
rester sous les limites de RunPod, d'où le MP3 192 kbit/s à l'aller (~2,9 Mo pour 4 minutes).

## Mesuré au premier build réussi (20/09/2026)

| | |
|---|---|
| Poids embarqués | **9,4 Go** (`acestep-v15-base` + LM 5 Hz + VAE + embedding) |
| Durée du build | **11 minutes** sur un runner `ubuntu-latest` |
| Tags publiés | `:latest` et `:<numéro de run>` |

## Construire

Tout se passe sur GitHub Actions — **rien à installer sur le PC** :
onglet *Actions* → « Construire et publier l'image » → *Run workflow*.
Le résultat : `ghcr.io/quang101182/acestep-serverless:latest`.

⚠️ Un runner GitHub n'a qu'environ 14 Go de libre : le workflow commence par récupérer la place des
outils préinstallés (~45 Go), sinon la construction échoue faute d'espace.

## Créer l'endpoint RunPod

1. Serverless → New Endpoint → image `ghcr.io/quang101182/acestep-serverless:latest`
2. GPU **24 Go** (RTX A5000 ≈ 0,16 $/h — le moteur monte à 7,4 Go de pointe, 16 Go suffisent mais
   laissent peu de marge)
3. **Min workers = 0** ← la ligne qui garantit qu'on ne paie rien à vide. Max workers = 1.
4. Idle timeout court (5 s) : au-delà, on paie un worker qui ne fait rien.

## Ce que ça coûte, en vrai

Un enrichissement de 3 minutes ≈ **0,01 $** (0,16 $/h × ~4 min avec la mise en route).
Au repos : **0 $**. Pas de volume, pas de worker allumé, pas de stockage facturé.
