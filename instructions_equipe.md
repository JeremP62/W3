# Guide d'utilisation en équipe - Aurora Star (Localisation 2D)

Pour que vous et vos deux collègues puissiez utiliser ce système avec vos ordinateurs (comme Anchors) et vos téléphones (comme Badges), voici la marche à suivre.

## Prérequis

1. **Réseau Local** : Vous devez tous les trois être connectés au **même réseau WiFi** (ou l'un de vous peut faire un partage de connexion).
2. **Installation** : Chacun doit avoir copié ce dossier et installé les dépendances via les commandes initiales (`python -m venv .venv`, etc., voir l'historique de la conversation).

## Rôle 1 : Le Serveur (Vous)

Vous allez héberger la base de données et l'affichage des positions.
1. Lancez le script : `.\start_server.ps1`
2. Le terminal va afficher une ligne en vert : **`IP à donner à vos collègues : 192.168.X.X`**. Notez bien cette IP.
3. Lancez aussi votre propre Anchor (dans un autre terminal) : `.\start_anchor.ps1`. 
   - Laissez l'IP par défaut (`127.0.0.1`) 
   - Choisissez l'identifiant `A1`.

## Rôle 2 : Les Anchors (Vos collègues)

Vos deux collègues vont agir comme des antennes relais supplémentaires.
1. Ils lancent le script : `.\start_anchor.ps1`
2. Le script va leur demander leur identifiant d'Anchor. Qu'ils choisissent **`A2`** pour l'un, et **`A3`** pour l'autre.
3. Le script va demander l'IP du serveur. Ils doivent entrer l'adresse IP que vous avez notée à l'étape du serveur (ex: `192.168.X.X`).

## Rôle 3 : Les Badges (Vos téléphones)

Pour être détectés par les Anchors, vos téléphones doivent émettre un signal Bluetooth spécifique.

1. Téléchargez une application de simulation BLE (par exemple **nRF Connect for Mobile** ou **BLE Scanner** sur iOS/Android).
2. Créez un "Advertiser" (ou diffuseur) avec un nom local.
3. **Important** : Le nom du périphérique (Local Name) *doit* commencer par `ASTRA-`. 
   - Exemple pour vous : `ASTRA-EDOUARD`
   - Exemple collègue 1 : `ASTRA-PAUL`
   - Exemple collègue 2 : `ASTRA-MARIE`
4. Activez la diffusion. 

## Résultat

Dès que les téléphones diffusent, les terminaux `anchor.ps1` commenceront à afficher la détection des téléphones. Le serveur récupèrera les distances de `A1`, `A2` et `A3` pour calculer la position 2D (trilatération) et vous verrez vos mouvements sur la carte !
