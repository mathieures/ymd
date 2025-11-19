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

### Installation avec uv

Il est aussi possible d’installer la CLI avec `uv` après avoir téléchargé le `.tar.gz` :
```sh
uv tool install (ls ymd-*.tar.gz)
```

De même qu’avec `pip`, la CLI pourra se lancer en exécutant `ymd`.

### Commandes

Les commandes suivantes sont disponibles avec la CLI :
- `list` (alias : `ls`) : liste les fichiers téléversés
- `download <fichier_sur_yahoo> <fichier_local>` (alias : `d`) : télécharge un fichier
- `upload <fichier_local>` (alias : `u`) : téléverse un fichier
- `remove <fichier_sur_yahoo>` (alias : `rm`) : supprime un fichier
- `list-folders` (alias : `lsf`) : liste les dossiers existants

### Arguments globaux

Certains paramètres peuvent être donnés à n’importe quelle commande pour changer le comportement de la CLI :
- `-h/--help` : affiche l’aide expliquant les arguments disponibles pour la commande utilisée
- `-c/--credentials` (défaut : `credentials.toml`, `~/.config/ymd/credentials.toml`) : définit où chercher les informations de connexion
- `-f/--folder` (défaut : `ymd`) : le dossier de destination des mails
- `--debug` : active le mode débug, affichant plus d’informations sur ce qui est fait par la CLI

## Tâches manuelles

Bien que la CLI permette d’effectuer la plupart des actions attendues d’un gestionnaire de stockage en ligne, quelques unes sont plus complexes que les autres voire impossibles. Elles sont résumées dans le tableau ci-dessous.

|        Action        | Comment l’effectuer                                         |
| :------------------: | ----------------------------------------------------------- |
|   Créer un dossier   | Utiliser une commande en ciblant le dossier voulu avec `-f` |
| Supprimer un dossier | Impossible                                                  |

## Motivation

YahooMail propose 1To de stockage de mail gratuit, mais restreint la taille des pièces jointes. 1To de stockage en ligne gratuit n’étant pas négligeable de nos jours, ce projet est né de la volonté de profiter de ce stockage sans limite de taille de fichier.