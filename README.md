# YMD (Yahoo Mail Drive)

Outil en ligne de commandes permettant de stocker des fichiers sur YahooMail.

## Prérequis

- Python ⩾ 3.14 (les versions précédentes n’ont pas été testées)
- Un fichier `credentials.toml` contenant les clés `address` et `password` (voir [la documentation pour générer un mot de passe d’application](https://login.yahoo.com/account/security?.lang=fr-FR&.intl=fr&.src=yhelp))

## Utilisation

Le script peut être utilisé avec Python directement, ou alors être installé comme paquet, ce qui rendra disponible un exécutable `ymd`.

### Sans installation

Puisqu’aucune dépendance n’est requise, on peut lancer la CLI avec :
```sh
py -m ymd.cli
```

### Installation avec pip

Pour avoir accès à la CLI comme exécutable, télécharger le fichier `.tar.gz` le plus récent dans les [Releases GitLab](https://gitlab.com/mathieures/ymd/-/releases) ou les [Releases GitHub](https://github.com/mathieures/ymd/releases), puis l’installer avec :
```sh
pip install ymd-*.tar.gz
```

La CLI pourra se lancer avec :
```sh
ymd
```

### Installation avec uv

Il est aussi possible d’installer la CLI avec `uv` après avoir téléchargé le `.tar.gz` :
```sh
uv tool install ymd-*.tar.gz
```

De même qu’avec `pip`, la CLI pourra se lancer en exécutant `ymd`.

### Commandes

Les commandes suivantes sont disponibles avec la CLI :

| Commande                                     | Alias | Description                               |
| -------------------------------------------- | ----- | ----------------------------------------- |
| `list`                                       | `ls`  | Liste les fichiers et dossiers téléversés |
| `download <fichier_sur_yahoo> <destination>` | `d`   | Télécharge un fichier                     |
| `upload <fichier_local>`                     | `u`   | Téléverse un fichier ou un dossier        |
| `remove <fichier_sur_yahoo>`                 | `rm`  | Supprime un fichier                       |
| `list-folders`                               | `lsf` | Liste les dossiers existants              |


### Arguments globaux

Les arguments suivants peuvent être donnés à n’importe quelle commande pour changer le comportement de la CLI :
- `-h/--help` : affiche l’aide expliquant les arguments disponibles pour la commande utilisée
- `-c/--credentials` (défaut : `credentials.toml`, `~/.config/ymd/credentials.toml`) : définit où chercher les informations de connexion
- `-f/--folder` (défaut : `ymd`) : le dossier de destination des mails
- `--debug` : active le mode débug, affichant plus d’informations sur ce qui est fait par la CLI

## Exemples

Les exemples listés ci-dessous requièrent un fichier `credentials.toml` valide pour être exécutés.

### Téléverser un fichier dans le dossier par défaut

```sh
ymd upload ./exemple.txt
```

### Téléverser un fichier dans un sous-dossier (en le créant s’il n’existe pas)

```sh
ymd upload ./exemple.txt --folder dossier/sous-dossier
```

### Téléverser un dossier récursivement

```sh
ymd upload ./exemple/ --folder dossier/sous-dossier/exemple
```

### Lister les fichiers et sous-dossiers dans un dossier (en le créant s’il n’existe pas)

```sh
ymd list --folder dossier/sous-dossier
```

### Lister les fichiers et sous-dossiers récursivement dans un dossier (en le créant s’il n’existe pas)

```sh
ymd list --folder dossier/sous-dossier --recurse
```

### Télécharger un fichier dans le dossier par défaut

```sh
ymd download exemple.txt ./exemple-téléchargé.txt
```

### Télécharger un fichier dans un sous-dossier

```sh
ymd download exemple.txt téléchargé.txt --folder dossier/sous-dossier
```

## Autres actions

La CLI permet d’effectuer la plupart des actions attendues d’un gestionnaire de stockage en ligne, cependant certaines sont plus complexes, voire impossibles et doivent être effectuées depuis l’interface web de YahooMail. Elles sont résumées dans le tableau ci-dessous.

|            Action             | Comment l’effectuer                     |
| :---------------------------: | --------------------------------------- |
|     Supprimer un dossier      | Impossible depuis la CLI pour le moment |
| Lister seulement les fichiers | Utiliser `--recurse` et `--max-depth 0` |

## Motivation

YahooMail propose 1To de stockage de mail gratuit, mais restreint la taille des pièces jointes à environ 29Mo. À but éducatif, cet outil est né de la volonté d’exploiter ce stockage sans limite de taille de fichier.