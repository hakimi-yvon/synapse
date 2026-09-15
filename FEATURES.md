# ⚡ Synapse — Documentation Complète des Fonctionnalités

> **Synapse** est une plateforme autonome d'intelligence stratégique, de veille d'actualités haute fidélité, de génération de podcasts radio IA et d'interaction conversationnelle omnicanale.

---

## 📑 Table des Matières

1. [Vue d'Ensemble & Architecture](#1-vue-densemble--architecture)
2. [Ingestion Multi-Sources & Normalisation](#2-ingestion-multi-sources--normalisation)
3. [Clustering Sémantique & Moteur Vectoriel](#3-clustering-sémantique--moteur-vectoriel)
4. [Synthèse Journalistique & Scoring IA](#4-synthèse-journalistique--scoring-ia)
5. [Duo Radio : Podcast Matinal à Deux Voix](#5-duo-radio--podcast-matinal-à-deux-voix)
6. [Infographie Visuelle de Synthèse HD](#6-infographie-visuelle-de-synthèse-hd)
7. [Voice-to-Voice : Interaction par Notes Vocales Telegram](#7-voice-to-voice--interaction-par-notes-vocales-telegram)
8. [Watchlist Intelligente & Alertes Ciblées](#8-watchlist-intelligente--alertes-ciblées)
9. [Alertes Flashs & Breaking News en Temps Réel](#9-alertes-flashs--breaking-news-en-temps-réel)
10. [Réveil Matinal Automatisé & Multi-Fuseaux Horaires](#10-réveil-matinal-automatisé--multi-fuseaux-horaires)
11. [Apprentissage Vectoriel & Recommandation Personnalisée](#11-apprentissage-vectoriel--recommandation-personnalisée)
12. [Chat with your News : RAG Contextuel Interactif](#12-chat-with-your-news--rag-contextuel-interactif)
13. [Dashboard Web & Archives Audio](#13-dashboard-web--archives-audio)
14. [Guide Complet des Commandes Telegram](#14-guide-complet-des-commandes-telegram)
15. [Exécution Locale & Déploiement](#15-exécution-locale--déploiement)

---

## 1. Vue d'Ensemble & Architecture

Synapse orchestre un pipeline complet, allant de la capture continue de flux d'informations mondiaux jusqu'à la restitution personnalisée par la voix, l'image et le texte.

```
       [ Sources d'Informations (RSS, Web, Reddit, HN) ]
                               │
                               ▼
            [ Ingestion & Déduplication Temps Réel ]
                               │
                               ▼
        [ Vectorisation Sémantique (Embeddings 768d) ]
                               │
                               ▼
         [ Clustering Automatique par Topic (pgvector) ]
                               │
                               ▼
          [ Analyse & Scoring Éditorial (Gemini Flash) ]
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
  [ Duo Radio TTS ]   [ Infographie HD ]    [ Digest Texte ]
   (Henri & Denise)        (Pillow)           (Markdown)
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                               ▼
            [ Diffusion Multi-Canale & Interaction ]
       ┌───────────────────────┴───────────────────────┐
       ▼                                               ▼
[ Bot Telegram Interactif ]                 [ Dashboard Web Moderne ]
- Podcast Audio Duo                         - Lecteur Audio Streaming
- Carte Infographie HD                      - Affichage Infographie HD
- Réponses Vocales (Voice-to-Voice)         - Revue Éditoriale & Sources
- Watchlist & Breaking News                 - Archives & Historique
```

### Stack Technologique
* **Backend** : Django 6 (Python 3.14)
* **Base de données & Vecteurs** : PostgreSQL avec l'extension `pgvector`
* **File de tâches & Planification** : Celery & Celery Beat avec Redis
* **Modèles d'Intelligence Artificielle** :
  * **Gemini 2.5 Flash** (`google-genai`) : Synthèse éditoriale, scoring, RAG et transcription audio multimodale.
  * **Sentence Transformers** : Vectorisation textuelle (embeddings 768 dimensions).
* **Génération Vocale (TTS)** : Microsoft Edge Neural TTS (`edge-tts`) avec voix studio françaises.
* **Moteur Audio** : FFmpeg pour le découpage, les silences radio et le mixage des pistes.
* **Génération Graphique** : Pillow (PIL) pour le rendu des infographies.
* **Frontend Web** : Django Templates, Tailwind CSS, Glassmorphism, FontAwesome.

---

## 2. Ingestion Multi-Sources & Normalisation

Synapse surveille et ingère automatiquement l'actualité à partir de multiples types de flux :

* **Connecteurs natifs pris en charge** :
  * **Flux RSS / Atom standard** : Blogs spécialisés, journaux économiques, médias tech (*TechCrunch, Les Numériques, Le Monde Informatique, etc.*).
  * **Hacker News API (`hn`)** : Récupération des articles tendance et discussions clés.
  * **Reddit (`reddit`)** : Veille sur les subreddits technologiques et financiers.
  * **Scraping Web & Médias** : Extraction du texte brut, filtrage du bruit HTML.
* **Caractéristiques clés** :
  * **Déduplication robuste** : Vérification stricte des URLs uniques en base.
  * **Horodatage universel** : Normalisation de toutes les publications en heure UTC.
  * **Orchestration asynchrone** : Tâches distribuées Celery (`fetch_source`, `fetch_all_sources`) garantissant zéro blocage.

---

## 3. Clustering Sémantique & Moteur Vectoriel

Synapse ne se contente pas de lister des articles individuels : il identifie les grands événements d'actualité en regroupant les articles similaires :

* **Modèle Vectoriel** : Chaque article est vectorisé dans un espace à 768 dimensions.
* **Indexation `pgvector`** : Recherche instantanée de plus proches voisins par distance cosinus directement dans PostgreSQL.
* **Clustering Incrémental par Topic** :
  * Si un article traite d'un sujet déjà existant (distance cosinus < seuil), il est automatiquement rattaché au `Topic` correspondant.
  * Le centroïde vectoriel du `Topic` est recalculé dynamiquement à chaque nouvel ajout.
  * Si l'article traite d'un événement inédit, un nouveau `Topic` est créé.

---

## 4. Synthèse Journalistique & Scoring IA

Chaque groupe d'articles (`Topic`) est soumis à Gemini Flash qui agit comme rédacteur en chef automatique :

* **Titre Journalistique** : Création d'un titre percutant et clair (max 120 caractères).
* **Points Clés (Bullets)** : Synthèse de 3 points factuels majeurs résumant les faits, sans redondance.
* **Score d'Importance (1 à 10)** : Évaluation de l'impact global de l'événement (un score ≥ 8 indique une actualité majeure ; un score ≥ 9 signale une urgence).
* **Détection Breaking News** : Détection automatique des événements critiques nécessitant une diffusion immédiate.
* **Catégorisation Thématique** : Classement dans une catégorie dédiée (*Tech, IA, Startups, Dev, Finance, etc.*).

---

## 5. Duo Radio : Podcast Matinal à Deux Voix

Fini les synthèses vocales monotones : Synapse propose un podcast matinal sous la forme d'une **véritable matinale radio animée par un duo de journalistes complices**.

### Les Deux Animateurs Neuronaux
* **Henri** (`fr-FR-HenriNeural`) :
  * *Rôle* : Présentateur principal.
  * *Style* : Voix masculine posée, chaleureuse, accueillante, introduisant les thèmes majeurs et assurant les transitions.
* **Denise** (`fr-FR-DeniseNeural`) :
  * *Rôle* : Co-présentatrice et analyste.
  * *Style* : Voix féminine vive, énergique, apportant les chiffres clés, les analyses techniques et les perspectives.

### Pipeline de Mixage Audio Studio
1. **Génération du Dialogue Scénarisé** : Gemini génère un script alterné dynamique avec les balises `[HENRI]:` et `[DENISE]:`.
2. **Synthèse Segmentée** : Chaque réplique est vocalisée indépendamment avec sa voix neuronale respective.
3. **Respiration Radio & Silences** : Insertion automatique d'un micro-silence de 0,25s entre chaque prise de parole pour un rythme naturel.
4. **Mixage FFmpeg Haute Fidélité** : Assemblage sans perte au format MP3 stéréo 128 kbps.

---

## 6. Infographie Visuelle de Synthèse HD

Pour chaque briefing matinal, Synapse génère automatiquement une **carte visuelle HD (1080 × 1350 px)** aux couleurs cyberpunk de l'application.

* **Composants du Visuel** :
  * **Header** : Logo de marque *SYNAPSE*, badge *DAILY DIGEST* et date complète.
  * **3 Cartes Thématiques** :
    * Badges de catégorie colorés (`[TECH]` en bleu cyan, `[IA]` en violet, `[FINANCE]` en jaune, etc.).
    * Score d'importance étoilé (ex: `★ 9/10`).
    * Titre de l'actualité avec découpage typographique automatique.
    * Points clés synthétiques mis en valeur par des puces lumineuses.
  * **Footer** : Signature de marque et date.
* **Intégration** :
  * Envoyée automatiquement sur Telegram avec le podcast via `sendPhoto`.
  * Affichée sur le Dashboard Web et la page détaillée avec options de prévisualisation plein écran et de téléchargement.

---

## 7. Voice-to-Voice : Interaction par Notes Vocales Telegram

Synapse permet une **interaction orale bidirectionnelle complète** sur Telegram : l'utilisateur peut parler au bot, et le bot lui répond par la voix.

### Déroulement d'une Session Voice-to-Voice
1. **Envoi d'un message vocal** : L'utilisateur enregistre et transmet une note vocale sur Telegram.
2. **Extraction & Décodage** : Le bot télécharge le flux audio OGG/Opus.
3. **Compréhension Multimodale Gemini** : Le fichier audio est transmis directement à **Gemini 2.5 Flash Multimodal** pour une retranscription fidèle et une analyse sémantique.
4. **Interrogation RAG** : La question transcrite est confrontée aux dépêches récentes via le moteur vectoriel pgvector.
5. **Vocalisation de la Réponse** : La réponse journalistique est synthétisée en voix neuronale de studio.
6. **Double Réponse Immédiate** :
   * Une **bulle vocale Telegram native (`sendVoice`)** avec onde audio jouable immédiatement.
   * La **réponse textuelle détaillée** avec puces et liens sources pour consultation ultérieure.

---

## 8. Watchlist Intelligente & Alertes Ciblées

La Watchlist permet de surveiller des sujets, entreprises, technologies ou personnes spécifiques (*ex: OpenAI, Nvidia, Mistral, Bitcoin, Sam Altman*).

* **Surveillance en continu** : Dès qu'un article est ingéré dans la base, il est scanné pour vérifier s'il correspond à une veille active (`check_article_watchlists_task`).
* **Alerte Immédiate** : L'utilisateur reçoit une notification instantanée contenant le titre, la source et le lien de l'article dès sa parution, sans attendre le briefing du lendemain.
* **Commandes Utilisateur** :
  * `/suivre <sujet>` : Ajoute un sujet à la surveillance.
  * `/mes_sujets` : Affiche les veilles actives et le nombre d'alertes déjà déclenchées.
  * `/arreter_suivi <sujet ou numéro>` : Désactive une veille.

---

## 9. Alertes Flashs & Breaking News en Temps Réel

Synapse surveille en permanence le flux mondial pour alerter les utilisateurs des bouleversements majeurs :

* **Déclencheur d'Urgence** : Tout `Topic` dont le score d'importance calculé est **≥ 9/10** ou tagué `is_breaking_news=True`.
* **Diffusion Push Prioritaire** : Notification Telegram instantanée avec signal visuel d'urgence `🚨 FLASH INFO / BREAKING NEWS`.
* **Contrôle Utilisateur** :
  * `/alertes on` : Activer la réception des flashs urgents.
  * `/alertes off` : Désactiver les flashs (pour ne garder que le réveil matinal).
* **Anti-Spam** : Horodatage `alert_sent_at` empêchant la répétition d'une même alerte.

---

## 10. Réveil Matinal Automatisé & Multi-Fuseaux Horaires

Synapse agit comme votre journal de bord matinal personnel, calé sur vos horaires réels :

* **Horaires Personnalisés** : Chaque utilisateur choisit l'heure exacte de livraison de son briefing (par défaut 07:00).
* **Gestion Avancée des Fuseaux Horaires (IANA)** :
  * Prise en charge universelle (ex: `Africa/Douala`, `Europe/Paris`, `America/Montreal`, etc.).
  * Calcul de l'heure locale exacte de l'utilisateur par rapport à l'horloge UTC du serveur.
* **Moteur d'Orchestration Celery Beat** :
  * Tâche `dispatch_scheduled_morning_digests` exécutée toutes les 10 minutes.
  * Détection des utilisateurs entrant dans leur fenêtre matinale.
  * Verrouillage via le cache Redis (`scheduled_digest_dispatched:{user_id}:{date}`) garantissant un envoi unique et sans doublon par jour.

---

## 11. Apprentissage Vectoriel & Recommandation Personnalisée

Synapse intègre un algorithme d'apprentissage par renforcement qui affine vos briefings selon vos retours :

* **Boutons Inline Interactifs** :
  * Sous chaque briefing sur Telegram, deux boutons sont disponibles : `👍 Pertinent` et `👎 Pas pour moi`.
  * Également accessible par les commandes `/like` et `/dislike`.
* **Ajustement du Vecteur d'Intérêt (`interest_vector`)** :
  * L'algorithme déplace le vecteur de profil de l'utilisateur vers le centroïde des articles aimés et l'éloigne de ceux rejetés.
  * Projection sur la sphère unitaire (normalisation L2).
* **Sélection Personnalisée des Briefings** : Les topics du jour sont classés par proximité cosinus avec le profil de l'auditeur.

---

## 12. Chat with your News : RAG Contextuel Interactif

Synapse permet de dialoguer en direct avec l'ensemble des dépêches ingérées :

* **Recherche Vectorielle Approfondie** : Extraction des passages d'articles les plus pertinents par similarité sémantique.
* **Mémoire Conversationnelle Multi-Tours** : Conservation du fil de discussion en cache Redis pour poser des questions de suivi (*« Et quelles sont les conséquences pour les développeurs ? »*).
* **Commandes** :
  * `/ask <question>` : Poser une question directe.
  * Envoi direct d'un texte dans le chat Telegram.
  * `/reset` : Effacer l'historique de discussion.

---

## 13. Dashboard Web & Archives Audio

Une interface web épurée et moderne permet de superviser l'ensemble de la plateforme depuis n'importe quel navigateur :

### Fonctionnalités du Dashboard
* **Métriques en Temps Réel** : Nombre total d'articles ingérés, sources actives, clusters sémantiques formés et alertes urgentes.
* **Lecteur Audio Intégré** : Écoute en streaming du dernier podcast Duo Radio avec bouton de téléchargement direct du MP3.
* **Vitrine Infographie HD** : Visualisation de la carte graphique du jour avec mode agrandi.
* **Revue de Presse Éditoriale** : Script complet rédigé avec mise en avant des sources et des catégories.
* **Bouton d'Action Immédiate** : Bouton *« Actualiser & Générer »* pour forcer la collecte des flux et la production d'un digest à la demande.
* **Bibliothèque d'Archives** ([`/archives/`](http://127.0.0.1:8000/archives/)) : Calendrier et liste de tous les briefings précédents avec réécoute audio et accès aux fiches détaillées.
* **Administration Django** ([`/admin/`](http://127.0.0.1:8000/admin/)) : Gestion fine des utilisateurs, des sources et des canaux de diffusion.

---

## 14. Guide Complet des Commandes Telegram

| Commande | Description | Exemple d'utilisation |
| :--- | :--- | :--- |
| **🎙️ Note Vocale** | Posez une question au micro, Synapse répond en vocal | *(Maintenir le micro Telegram)* |
| `/start` | Initialiser le bot et configurer vos centres d'intérêt | `/start` |
| `/digest` | Générer et recevoir immédiatement votre briefing complet | `/digest` |
| `/suivre <sujet>` | Ajouter un sujet ou une entreprise à la Watchlist | `/suivre OpenAI` |
| `/mes_sujets` | Lister vos sujets sous surveillance et le nombre d'alertes | `/mes_sujets` |
| `/arreter_suivi <sujet>` | Arrêter la surveillance d'un sujet | `/arreter_suivi OpenAI` |
| `/ask <question>` | Poser une question sur l'actualité récente (RAG) | `/ask Quels sont les nouveaux modèles d'IA ?` |
| `/heure <HH:MM>` | Modifier l'heure de livraison matinale du briefing | `/heure 07:30` ou `/heure 8h` |
| `/fuseau <Zone>` | Modifier votre fuseau horaire de référence | `/fuseau Europe/Paris` |
| `/alertes <on\|off>` | Activer ou désactiver les alertes Breaking News | `/alertes on` |
| `/like` ou `👍` | Noter positivement le dernier briefing reçu | `/like` |
| `/dislike` ou `👎` | Noter négativement le briefing (affiner l'IA) | `/dislike` |
| `/topics` | Reconfigurer vos domaines suivis (Tech, IA, Finance...) | `/topics` |
| `/format <mode>` | Choisir le format de réception (`text`, `audio`, `both`) | `/format both` |
| `/status` | Afficher toute votre configuration active et vos stats | `/status` |
| `/reset` | Réinitialiser la mémoire du chat d'actualités | `/reset` |

---

## 15. Exécution Locale & Déploiement

### Lancement Rapide en Local

Pour lancer l'environnement complet :

```bash
# Option 1 : Lancement unifié de tous les services (Dashboard, Celery, Bot)
./run_local.sh

# Option 2 : Lancement individuel du serveur web
./venv/bin/python manage.py runserver

# Option 3 : Lancement du bot Telegram en mode synchrone autonome (sans worker)
./venv/bin/python manage.py run_telegram_bot --sync
```

### URLs Locales
* **Tableau de bord live** : [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* **Archives des podcasts** : [http://127.0.0.1:8000/archives/](http://127.0.0.1:8000/archives/)
* **Administration** : [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)
