# YMD (Yahoo Mail Drive)

Cet outil en ligne de commandes en Python pur permet de lister, télécharger et téléverser des fichiers sur YahooMail en créant des mails contenant des pièces jointes dans un dossier dédié. La limite de taille pour une pièce jointe étant d’environ 29Mo, les fichiers sont divisés en plusieurs morceaux de façon transparente lors du téléversement, puis rassemblés lors du téléchargement.

## Prérequis

- Python ⩾ 3.13 (les versions précédentes n’ont pas été testées)
- Un fichier `credentials.toml` contenant les clés `address` et `password` (voir [la documentation pour générer un mot de passe d’application](https://login.yahoo.com/account/security?.lang=fr-FR&.intl=fr&.src=yhelp))

## Utilisation

Le script peut être utilisé avec Python directement, ou alors être installé comme paquet, ce qui rendra disponible un exécutable `ymd`.

### Sans installation

Puisqu’aucune dépendance n’est requise, on peut lancer la CLI avec :
```sh
py -m ymd.cli
```

### Installation avec pip

Pour avoir accès à la CLI comme exécutable, il est possible de télécharger le paquet Python dans les [Releases GitLab](https://gitlab.com/mathieures/ymd/-/releases). Une fois le fichier `.tar.gz` téléchargé, il est installable dans un environnement virtuel ou globalement avec :
```sh
pip install (ls ymd-*.tar.gz)
```

La CLI s’utilise ensuite comme un exécutable normal :
```sh
ymd
```

### Commandes

Peu importe la façon dont est utilisée la CLI, trois commandes sont disponibles avec des aliases :
- `list` (alias : `ls`) : liste les fichiers téléversés
- `download <fichier_sur_yahoo> <fichier_local>` (alias : `d`) : télécharge un fichier
- `upload <fichier_local>` (alias : `u`) : téléverse un fichier
- `remove <fichier_sur_yahoo>` (alias : `rm`) : supprime un fichier

### Arguments

Certaines choses peuvent être paramétrées grâce à des arguments de la CLI :
- le fichier où se trouvent les informations de connexion avec `-c/--credentials` (défaut : `credentials.toml`, `~/.config/ymd/credentials.toml`) ;
- le dossier de destination des mails avec `-f/--folder` (défaut : `ymd`) ;
- le mode debug avec `--debug`, qui affiche plus d’informations sur ce qui est fait.

## Tâches manuelles

Bien que la CLI permette d’effectuer la plupart des actions voulues, elle n’offre pas autant de fonctionnalités que le site web officiel ; aussi les actions suivantes sont impossibles avec la CLI :
- supprimer un dossier ;
- créer un dossier sans téléverser de fichier.

## Motivation

YahooMail propose 1To de stockage de mail gratuit, mais restreint la taille des pièces jointes. 1To de stockage en ligne gratuit n’étant pas négligeable de nos jours, ce projet est né de la volonté de profiter de ce stockage sans limite de taille de fichier.