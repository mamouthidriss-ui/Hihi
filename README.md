# Swap Studio
Remplace le visage d'une vidéo par un avatar, en gardant le son. Mention « Généré par IA » ajoutée automatiquement.

## Lancer en local
    pip install -r requirements.txt   # + ffmpeg installé
    ENGINE=mock python app.py          # http://localhost:8000

## Déployer sur Render
1. Pousse ce dossier sur GitHub.
2. Render > New > Blueprint > choisis le dépôt (render.yaml est détecté).
3. Tu obtiens un lien public. Mode démo (ENGINE=mock) : simulation, sans vrai swap.

## Vrai face swap
Installe FaceFusion (https://github.com/facefusion/facefusion) dans ./facefusion sur une machine avec GPU NVIDIA,
puis lance avec ENGINE=facefusion. Adapte FF_CMD si la syntaxe de ta version diffère.
Vérifie la licence commerciale du modèle de swap avant tout usage payant.
Render (offre gratuite) n'a pas de GPU : prévois un serveur GPU pour le mode réel.
