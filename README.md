# YMD (Yahoo Mail Drive)

Cet outil en ligne de commandes permet de lister, télécharger et téléverser des fichiers sur YahooMail en créant des mails contenant des pièces jointes dans un dossier dédié. La limite de taille pour une pièce jointe étant d’environ 29Mo, les fichiers sont divisés en plusieurs morceaux de façon transparente lors du téléversement, puis rassemblés lors du téléchargement.

## Prérequis

- Python ⩾ 3.12
- Un fichier `credentials.toml` contenant les clés `address` et `password` (voir [générer un mot de passe d’application](https://login.yahoo.com/account/security?.lang=fr-FR&.intl=fr&.src=yhelp))

## Utilisation

Aucune dépendance n’est requise, le programme peut donc se lancer sans installation :
```sh
# Affiche l’aide
py ymd.py -h
# Liste les fichiers téléversés
py ymd.py list
# Télécharge le fichier "fichier_sur_yahoo.txt" et le sauvegarde dans "fichier_local.txt"
py ymd.py download fichier_sur_yahoo.txt fichier_local.txt
# Téléverse le fichier "fichier_local.txt"
py ymd.py upload fichier_local.txt
```

Un paramètre `--debug` est disponible pour afficher plus de logs.

## Paramétrage

Peu de choses ont besoin d’être paramétrées, mais quelques unes peuvent l’être en modifiant `ymd.py` :
- le nom du dossier créé dans la boîte mail, en modifiant la variable `YMD_FOLDER_NAME` (défaut : `ymd`) ;
- le niveau de logs par défaut, en modifiant la variable `YMD_DEFAULT_LOG_LEVEL` (défaut : `ymd`) ;

## Motivation

YahooMail propose 1To de stockage de mail gratuit, mais restreint la taille des pièces jointes. 1To de stockage en ligne gratuit n’étant pas négligeable de nos jours, ce projet est né de la volonté de profiter de ce stockage sans limite de taille.