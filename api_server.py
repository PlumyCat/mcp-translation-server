#!/usr/bin/env python3
"""
Serveur API REST simple pour la traduction de documents
Compatible avec Copilot Studio via webhooks HTTP
"""

from src.config import Config
from src.services.graph_service import GraphService
from src.services.translation_service import TranslationService
from src.services.blob_service import BlobService
from pathlib import Path
import sys
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from aiohttp import web, ClientSession
from aiohttp.web import Request, Response, RouteTableDef
import aiohttp_cors

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import des services locaux
sys.path.insert(0, str(Path(__file__).parent))


# Routes
routes = RouteTableDef()

# Stockage des traductions en cours (en production, utiliser Redis)
active_translations: Dict[str, Dict[str, Any]] = {}


@routes.get('/health')
async def health_check(request: Request) -> Response:
    """Point de santé pour vérifier que le serveur fonctionne"""

    # Si l'en-tête Accept contient text/html, retourner une page HTML
    accept_header = request.headers.get('Accept', '')
    if 'text/html' in accept_header:
        return await health_page(request)

    # Sinon retourner du JSON pour les APIs
    return web.json_response({
        "status": "healthy",
        "service": "translation-api",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    })


async def health_page(request: Request) -> Response:
    """Page HTML de santé du serveur"""

    # Test des services
    blob_status = "✅ Connecté"
    translation_status = "✅ Connecté"
    graph_status = "⚠️ Non configuré"

    try:
        blob_service = BlobService()
        blob_status = "✅ Connecté"
    except Exception as e:
        blob_status = f"❌ Erreur: {str(e)[:50]}..."

    try:
        translation_service = TranslationService()
        translation_status = "✅ Connecté"
    except Exception as e:
        translation_status = f"❌ Erreur: {str(e)[:50]}..."

    try:
        graph_service = GraphService()
        if graph_service.enabled:
            graph_status = "✅ Configuré"
        else:
            graph_status = "⚠️ Non configuré (optionnel)"
    except Exception as e:
        graph_status = f"❌ Erreur: {str(e)[:50]}..."

    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🔍 Santé du Serveur - MCP Translation</title>
        <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 800px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }}
            .header {{ 
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                color: white; 
                padding: 30px; 
                border-radius: 10px; 
                text-align: center; 
                margin-bottom: 30px;
            }}
            .card {{ 
                background: white; 
                padding: 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
                margin-bottom: 20px;
            }}
            .status-item {{
                display: flex;
                justify-content: space-between;
                padding: 10px;
                margin: 5px 0;
                background: #f8f9fa;
                border-radius: 5px;
                border-left: 4px solid #28a745;
            }}
            .status-error {{
                border-left-color: #dc3545;
            }}
            .status-warning {{
                border-left-color: #ffc107;
            }}
            .nav-links {{
                text-align: center;
                margin-top: 20px;
            }}
            .nav-links a {{
                display: inline-block;
                margin: 0 10px;
                padding: 10px 20px;
                background: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background-color 0.3s;
            }}
            .nav-links a:hover {{
                background: #0056b3;
            }}
            .timestamp {{
                font-family: monospace;
                font-size: 0.9em;
                color: #6c757d;
            }}
        </style>
        <script>
            // Auto-refresh toutes les 30 secondes
            setTimeout(() => location.reload(), 30000);
        </script>
    </head>
    <body>
        <div class="header">
            <h1>🔍 Santé du Serveur</h1>
            <p>Surveillance en temps réel des services</p>
            <p class="timestamp">Dernière vérification: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
        
        <div class="card">
            <h2>📊 État des Services</h2>
            <div class="status-item">
                <span><strong>🌐 Serveur API</strong></span>
                <span>✅ En ligne</span>
            </div>
            <div class="status-item">
                <span><strong>💾 Azure Storage</strong></span>
                <span>{blob_status}</span>
            </div>
            <div class="status-item">
                <span><strong>🌍 Azure Translator</strong></span>
                <span>{translation_status}</span>
            </div>
            <div class="status-item">
                <span><strong>☁️ MS Graph (OneDrive)</strong></span>
                <span>{graph_status}</span>
            </div>
        </div>
        
        <div class="card">
            <h2>📈 Statistiques</h2>
            <div class="status-item">
                <span><strong>Traductions actives</strong></span>
                <span>{len(active_translations)}</span>
            </div>
            <div class="status-item">
                <span><strong>Version API</strong></span>
                <span>1.0.0</span>
            </div>
            <div class="status-item">
                <span><strong>Uptime</strong></span>
                <span>Démarré aujourd'hui</span>
            </div>
        </div>
        
        <div class="nav-links">
            <a href="/">🏠 Accueil</a>
            <a href="/tools">🛠️ Outils</a>
            <a href="/translations">📊 Traductions</a>
        </div>
        
        <div class="card">
            <p><small>🔄 Cette page se rafraîchit automatiquement toutes les 30 secondes</small></p>
        </div>
    </body>
    </html>
    """

    return web.Response(text=html_content, content_type='text/html')


@routes.get('/tools')
async def list_tools(request: Request) -> Response:
    """Liste des outils disponibles (format compatible Copilot Studio)"""

    tools = [
        {
            "name": "translate_document",
            "description": "Traduit un document vers une langue cible. Supporte PDF, DOCX, TXT et autres formats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_content": {
                        "type": "string",
                        "description": "Contenu du fichier encodé en base64"
                    },
                    "file_name": {
                        "type": "string",
                        "description": "Nom du fichier avec extension"
                    },
                    "target_language": {
                        "type": "string",
                        "description": "Code langue cible (ex: 'fr', 'en', 'es', 'de')"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "Identifiant unique de l'utilisateur"
                    }
                },
                "required": ["file_content", "file_name", "target_language", "user_id"]
            }
        },
        {
            "name": "check_translation_status",
            "description": "Vérifie l'état d'une traduction en cours et retourne le statut actuel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "translation_id": {
                        "type": "string",
                        "description": "ID de la traduction à vérifier"
                    }
                },
                "required": ["translation_id"]
            }
        },
        {
            "name": "get_translation_result",
            "description": "Récupère le document traduit et l'enregistre sur OneDrive de l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "translation_id": {
                        "type": "string",
                        "description": "ID de la traduction terminée"
                    },
                    "save_to_onedrive": {
                        "type": "boolean",
                        "description": "Sauvegarder sur OneDrive (défaut: true)",
                        "default": True
                    }
                },
                "required": ["translation_id"]
            }
        }
    ]

    # Si l'en-tête Accept contient text/html, retourner une page HTML
    accept_header = request.headers.get('Accept', '')
    if 'text/html' in accept_header:
        return await tools_page(request, tools)

    # Sinon retourner du JSON pour les APIs
    return web.json_response({
        "tools": tools,
        "count": len(tools),
        "api_version": "1.0.0"
    })


async def tools_page(request: Request, tools: list) -> Response:
    """Page HTML des outils MCP"""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🛠️ Outils MCP - Translation Server</title>
        <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 1000px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }}
            .header {{ 
                background: linear-gradient(135deg, #007bff 0%, #6610f2 100%);
                color: white; 
                padding: 30px; 
                border-radius: 10px; 
                text-align: center; 
                margin-bottom: 30px;
            }}
            .tool-card {{ 
                background: white; 
                padding: 25px; 
                border-radius: 10px; 
                box-shadow: 0 4px 15px rgba(0,0,0,0.1); 
                margin-bottom: 25px;
                border-left: 5px solid #007bff;
            }}
            .tool-name {{
                font-size: 1.4em;
                font-weight: bold;
                color: #007bff;
                margin-bottom: 10px;
            }}
            .tool-description {{
                color: #6c757d;
                margin-bottom: 20px;
                line-height: 1.6;
            }}
            .parameters {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                border: 1px solid #e9ecef;
            }}
            .param-item {{
                margin: 10px 0;
                padding: 8px;
                background: white;
                border-radius: 5px;
                border-left: 3px solid #28a745;
            }}
            .param-name {{
                font-weight: bold;
                color: #495057;
            }}
            .param-type {{
                color: #007bff;
                font-family: monospace;
                font-size: 0.9em;
            }}
            .param-required {{
                color: #dc3545;
                font-size: 0.8em;
                font-weight: bold;
            }}
            .nav-links {{
                text-align: center;
                margin: 30px 0;
            }}
            .nav-links a {{
                display: inline-block;
                margin: 0 10px;
                padding: 12px 24px;
                background: #6c757d;
                color: white;
                text-decoration: none;
                border-radius: 25px;
                transition: all 0.3s;
            }}
            .nav-links a:hover {{
                background: #495057;
                transform: translateY(-2px);
            }}
            .stats {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                margin-bottom: 20px;
            }}
            .example-json {{
                background: #212529;
                color: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 0.9em;
                overflow-x: auto;
                margin-top: 15px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🛠️ Outils MCP</h1>
            <p>Documentation des outils de traduction</p>
            <p>Compatible avec Copilot Studio et autres clients MCP</p>
        </div>
        
        <div class="stats">
            <h2>📊 Statistiques</h2>
            <p><strong>{len(tools)}</strong> outils disponibles • Version API <strong>1.0.0</strong></p>
        </div>
    """

    for i, tool in enumerate(tools, 1):
        # Icônes pour chaque outil
        icons = {
            "translate_document": "🌍",
            "check_translation_status": "🔍",
            "get_translation_result": "📥"
        }
        icon = icons.get(tool["name"], "🛠️")

        html_content += f"""
        <div class="tool-card">
            <div class="tool-name">{icon} {tool["name"]}</div>
            <div class="tool-description">{tool["description"]}</div>
            
            <div class="parameters">
                <h4>📋 Paramètres :</h4>
        """

        if "parameters" in tool and "properties" in tool["parameters"]:
            for param_name, param_info in tool["parameters"]["properties"].items():
                is_required = param_name in tool["parameters"].get(
                    "required", [])
                required_badge = '<span class="param-required">REQUIS</span>' if is_required else ''

                html_content += f"""
                <div class="param-item">
                    <span class="param-name">{param_name}</span> 
                    <span class="param-type">({param_info.get("type", "unknown")})</span>
                    {required_badge}
                    <br><small>{param_info.get("description", "Pas de description")}</small>
                </div>
                """

        # Exemple JSON pour l'outil
        if tool["name"] == "translate_document":
            example = '''{
  "file_content": "SGVsbG8gV29ybGQ=",
  "file_name": "test.txt",
  "target_language": "fr", 
  "user_id": "user123"
}'''
        elif tool["name"] == "check_translation_status":
            example = '''{
  "translation_id": "abc123-def456"
}'''
        else:
            example = '''{
  "translation_id": "abc123-def456",
  "save_to_onedrive": true
}'''

        html_content += f"""
            </div>
            
            <div class="example-json">
                <strong>💡 Exemple d'utilisation :</strong><br>
                POST /translate (pour {tool["name"]})<br>
                Content-Type: application/json<br><br>
                {example}
            </div>
        </div>
        """

    html_content += """
        <div class="nav-links">
            <a href="/">🏠 Accueil</a>
            <a href="/health">🔍 Santé</a>
            <a href="/translations">📊 Traductions</a>
        </div>
        
        <div class="tool-card">
            <h3>🚀 Comment utiliser ces outils</h3>
            <p>1. <strong>Copilot Studio</strong> : Configurez un webhook vers <code>http://localhost:3000</code></p>
            <p>2. <strong>API directe</strong> : Envoyez des requêtes POST vers les endpoints</p>
            <p>3. <strong>Tests</strong> : Utilisez les exemples JSON ci-dessus</p>
        </div>
    </body>
    </html>
    """

    return web.Response(text=html_content, content_type='text/html')


@routes.post('/translate')
async def translate_document(request: Request) -> Response:
    """Lance une traduction de document à partir d'un blob existant"""

    try:
        data = await request.json()

        # Validation des paramètres pour la nouvelle logique
        required_fields = ["blob_name", "target_language", "user_id"]
        for field in required_fields:
            if field not in data:
                return web.json_response({
                    "success": False,
                    "error": f"Paramètre manquant: {field}"
                }, status=400)

        blob_name = data["blob_name"]
        target_language = data["target_language"]
        user_id = data["user_id"]

        logger.info(
            f"🚀 Nouvelle traduction: {blob_name} → {target_language} (utilisateur: {user_id})")

        # Services
        blob_service = BlobService()
        translation_service = TranslationService()

        # Étape 1: Vérification de l'existence du blob
        blob_exists = await blob_service.check_blob_exists(
            container=blob_service.input_container,
            blob_name=blob_name
        )

        if not blob_exists:
            return web.json_response({
                "success": False,
                "error": f"Fichier '{blob_name}' non trouvé dans le container {blob_service.input_container}"
            }, status=404)

        # Étape 2: Préparation des URLs pour la traduction
        blob_urls = await blob_service.prepare_translation_urls(
            input_blob_name=blob_name,
            target_language=target_language
        )

        # Étape 3: Démarrage de la traduction
        translation_id = await translation_service.start_translation(
            source_url=blob_urls["source_url"],
            target_url=blob_urls["target_url"],
            target_language=target_language
        )

        # Stockage des informations
        active_translations[translation_id] = {
            "blob_name": blob_name,
            "target_language": target_language,
            "user_id": user_id,
            "blob_urls": blob_urls,
            "status": "En cours",
            "started_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }

        return web.json_response({
            "success": True,
            "translation_id": translation_id,
            "message": f"Traduction démarrée avec succès pour {blob_name}",
            "status": "En cours",
            "target_language": target_language,
            "estimated_time": "2-5 minutes"
        })

    except Exception as e:
        logger.error(f"❌ Erreur traduction: {str(e)}")
        return web.json_response({
            "success": False,
            "error": f"Erreur lors de la traduction: {str(e)}"
        }, status=500)


@routes.get('/status/{translation_id}')
async def check_status(request: Request) -> Response:
    """Vérifie le statut d'une traduction"""

    try:
        translation_id = request.match_info['translation_id']

        if translation_id not in active_translations:
            return web.json_response({
                "success": False,
                "error": f"Traduction '{translation_id}' non trouvée"
            }, status=404)

        translation_service = TranslationService()

        # Vérification du statut via Azure
        status = await translation_service.check_translation_status(translation_id)

        # Mise à jour du statut local
        active_translations[translation_id]["status"] = status["status"]
        active_translations[translation_id]["last_checked"] = datetime.utcnow(
        ).isoformat()

        translation_info = active_translations[translation_id]

        response_data = {
            "success": True,
            "translation_id": translation_id,
            "status": status["status"],
            "file_name": translation_info.get("blob_name", translation_info.get("file_name", "Inconnu")),
            "target_language": translation_info["target_language"],
            "progress": status.get("progress", "En cours..."),
            "started_at": translation_info["started_at"]
        }

        # Ajout des détails d'erreur si nécessaire
        if status["status"] == "Failed":
            response_data["error"] = status.get("error", "Erreur inconnue")

        return web.json_response(response_data)

    except Exception as e:
        logger.error(f"❌ Erreur vérification statut: {str(e)}")
        return web.json_response({
            "success": False,
            "error": f"Erreur lors de la vérification: {str(e)}"
        }, status=500)


@routes.get('/result/{translation_id}')
async def get_result(request: Request) -> Response:
    """Récupère le résultat d'une traduction"""

    try:
        translation_id = request.match_info['translation_id']
        save_to_onedrive = request.query.get(
            'save_to_onedrive', 'true').lower() == 'true'

        translation_info = None

        # Vérifier d'abord si la traduction est en mémoire
        if translation_id in active_translations:
            translation_info = active_translations[translation_id]
        else:
            # Si pas en mémoire, essayer de deviner le fichier traduit
            logger.info(
                f"⚠️ Traduction {translation_id} non trouvée en mémoire, recherche du fichier...")

            # Rechercher dans le container doc-trad des fichiers avec pattern
            blob_service = BlobService()
            try:
                # Lister les fichiers dans doc-trad
                container_client = blob_service.blob_service_client.get_container_client(
                    blob_service.output_container
                )

                # Chercher un fichier récent qui pourrait correspondre
                recent_files = []
                for blob in container_client.list_blobs():
                    # Fichier modifié dans les dernières heures
                    # 2h
                    if blob.last_modified and (datetime.utcnow() - blob.last_modified.replace(tzinfo=None)).total_seconds() < 7200:
                        recent_files.append({
                            'name': blob.name,
                            'size': blob.size,
                            'last_modified': blob.last_modified,
                            'url': f"https://{blob_service.account_name}.blob.core.windows.net/{blob_service.output_container}/{blob.name}"
                        })

                if recent_files:
                    # Prendre le plus récent
                    recent_file = max(
                        recent_files, key=lambda x: x['last_modified'])
                    logger.info(
                        f"📄 Fichier récent trouvé: {recent_file['name']}")

                    # Créer une info de traduction artificielle
                    # Reconstruction du nom original à partir du nom traduit
                    # Format: {nom_original}-{langue}.{extension}
                    file_name = recent_file['name']
                    if '.' in file_name:
                        name_part, extension = file_name.rsplit('.', 1)
                        if '-' in name_part:
                            # Prendre tout sauf le dernier segment après le dernier tiret
                            # Ex: "Being cloud-ready and future-proof-es" -> "Being cloud-ready and future-proof"
                            original_name = name_part.rsplit('-', 1)[0]
                            target_language = name_part.rsplit('-', 1)[1]
                            blob_name = f"{original_name}.{extension}"
                        else:
                            # Pas de tiret dans le nom, utiliser tel quel
                            blob_name = file_name
                            target_language = "unknown"
                    else:
                        # Pas d'extension
                        if '-' in file_name:
                            original_name = file_name.rsplit('-', 1)[0]
                            target_language = file_name.rsplit('-', 1)[1]
                            blob_name = original_name
                        else:
                            blob_name = file_name
                            target_language = "unknown"

                    translation_info = {
                        "blob_name": blob_name,
                        "target_language": target_language,
                        "user_id": "unknown",
                        "blob_urls": {
                            "target_url": recent_file['url']
                        }
                    }
                else:
                    return web.json_response({
                        "success": False,
                        "error": f"Traduction '{translation_id}' non trouvée et aucun fichier récent dans le container"
                    }, status=404)

            except Exception as search_error:
                logger.error(f"❌ Erreur recherche fichier: {search_error}")
                return web.json_response({
                    "success": False,
                    "error": f"Traduction '{translation_id}' non trouvée en mémoire: {search_error}"
                }, status=404)

        # Services
        translation_service = TranslationService()
        blob_service = BlobService()
        graph_service = GraphService()

        # Approche pragmatique : essayer de télécharger le fichier traduit
        # Si ça marche, c'est que la traduction est finie, peu importe le statut
        logger.info(f"🔍 Vérification pragmatique pour {translation_id}")

        try:
            # Essai de téléchargement direct du fichier traduit
            translated_content = await blob_service.download_translated_file(
                translation_info["blob_urls"]["target_url"]
            )
            logger.info(
                f"✅ Fichier traduit téléchargé avec succès ({len(translated_content)} bytes)")

        except Exception as download_error:
            logger.warning(
                f"⚠️ Téléchargement direct échoué: {download_error}")

            # Si le téléchargement direct échoue, on fait le check de statut avec retry
            max_retries = 3
            status = None
            for retry in range(max_retries):
                status = await translation_service.check_translation_status(translation_id)
                logger.info(
                    f"🔄 Tentative {retry + 1}//{max_retries}: Statut Azure = '{status['status']}'")

                if status["status"] == "Succeeded":
                    logger.info(
                        f"✅ Statut confirmé 'Succeeded' à la tentative {retry + 1}")
                    break
                elif retry < max_retries - 1:
                    logger.info(f"⏳ Attente avant nouvelle vérification...")
                    await asyncio.sleep(5)  # Délai plus long
                else:
                    # Dernière tentative échouée
                    logger.error(
                        f"❌ Statut final après {max_retries} tentatives: {status['status']}")
                    return web.json_response({
                        "success": False,
                        "error": f"La traduction n'est pas encore terminée après {max_retries} vérifications (statut: {status['status']})"
                    }, status=400)

            # Nouveau téléchargement après confirmation du statut
            try:
                translated_content = await blob_service.download_translated_file(
                    translation_info["blob_urls"]["target_url"]
                )
                logger.info(
                    f"✅ Fichier traduit téléchargé après vérification statut ({len(translated_content)} bytes)")
            except Exception as final_error:
                logger.error(f"❌ Échec final du téléchargement: {final_error}")
                return web.json_response({
                    "success": False,
                    "error": f"Impossible de télécharger le fichier traduit: {final_error}"
                }, status=500)

        response_data = {
            "success": True,
            "translation_id": translation_id,
            "file_name": translation_info.get("blob_name", translation_info.get("file_name", "Inconnu")),
            "target_language": translation_info["target_language"],
            "file_size": len(translated_content),
            "completed_at": datetime.utcnow().isoformat()
        }

        # Import automatique vers OneDrive
        if graph_service.enabled:
            try:
                logger.info(
                    f"☁️ Import automatique vers OneDrive pour {translation_info['user_id']}")
                onedrive_url = await graph_service.save_to_onedrive(
                    user_id=translation_info["user_id"],
                    file_content=translated_content,
                    file_name=translation_info.get(
                        "blob_name", translation_info.get("file_name", "Inconnu")),
                    target_language=translation_info["target_language"]
                )
                response_data["onedrive_url"] = onedrive_url
                response_data["saved_to_onedrive"] = True
                logger.info(f"✅ Fichier sauvé sur OneDrive: {onedrive_url}")
            except Exception as e:
                logger.warning(f"⚠️ Échec sauvegarde OneDrive: {str(e)}")
                response_data["onedrive_error"] = str(e)
                response_data["saved_to_onedrive"] = False
        else:
            response_data["saved_to_onedrive"] = False
            response_data["onedrive_error"] = "Service OneDrive non configuré"

        # Nettoyage
        del active_translations[translation_id]

        return web.json_response(response_data)

    except Exception as e:
        logger.error(f"❌ Erreur récupération résultat: {str(e)}")
        return web.json_response({
            "success": False,
            "error": f"Erreur lors de la récupération: {str(e)}"
        }, status=500)


@routes.get('/translations')
async def list_active_translations(request: Request) -> Response:
    """Liste les traductions actives"""

    # Si l'en-tête Accept contient text/html, retourner une page HTML
    accept_header = request.headers.get('Accept', '')
    if 'text/html' in accept_header:
        return await translations_page(request)

    # Sinon retourner du JSON pour les APIs
    return web.json_response({
        "active_translations": len(active_translations),
        "translations": [
            {
                "id": tid,
                "file_name": info["file_name"],
                "target_language": info["target_language"],
                "status": info["status"],
                "started_at": info["started_at"]
            }
            for tid, info in active_translations.items()
        ]
    })


async def translations_page(request: Request) -> Response:
    """Page HTML des traductions actives"""

    # Statistiques
    total_translations = len(active_translations)
    status_counts = {}
    for info in active_translations.values():
        status = info.get("status", "Inconnu")
        status_counts[status] = status_counts.get(status, 0) + 1

    # Génération du HTML pour les traductions
    translations_html = ""
    if total_translations == 0:
        translations_html = """
        <div class="translation-table">
            <div class="table-header">
                📋 Aucune traduction active
            </div>
            <div class="empty-state">
                <div class="empty-icon">🌍</div>
                <h3>Aucune traduction en cours</h3>
                <p>Lancez une nouvelle traduction via l'API pour voir les détails ici.</p>
                <p><strong>Endpoint:</strong> <code>POST /translate</code></p>
            </div>
        </div>
        """
    else:
        translations_html = """
        <div class="translation-table">
            <div class="table-header">
                📋 Traductions en cours
            </div>
            <div class="translation-row" style="background: #e9ecef; font-weight: bold;">
                <div>📄 Fichier</div>
                <div>🆔 ID de Traduction</div>
                <div>🌍 Langue</div>
                <div>📊 Statut</div>
                <div>⏰ Démarré</div>
            </div>
        """

        for tid, info in active_translations.items():
            file_name = info.get("blob_name", info.get("file_name", "Inconnu"))
            target_language = info.get("target_language", "??")
            status = info.get("status", "Inconnu")
            started_at = info.get("started_at", 0)

            # Badge de statut
            status_class = "status-pending"
            if status == "Succeeded":
                status_class = "status-succeeded"
            elif status == "Failed":
                status_class = "status-failed"
            elif status in ["En cours", "InProgress"]:
                status_class = "status-inprogress"

            # Formatage du timestamp
            try:
                start_time = datetime.fromtimestamp(
                    started_at).strftime('%H:%M:%S')
            except:
                start_time = "N/A"

            # Échapper les caractères spéciaux pour HTML
            file_name_display = file_name[:30] + \
                ("..." if len(file_name) > 30 else "")
            tid_display = tid[:12] + "..."

            translations_html += f"""
            <div class="translation-row">
                <div title="{file_name}">{file_name_display}</div>
                <div title="{tid}">{tid_display}</div>
                <div>{target_language.upper()}</div>
                <div><span class="status-badge {status_class}">{status}</span></div>
                <div class="timestamp">{start_time}</div>
            </div>
            """

        translations_html += "</div>"

    # Timestamp actuel
    current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>📊 Traductions Actives - MCP Translation</title>
        <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }}
            .header {{ 
                background: linear-gradient(135deg, #17a2b8 0%, #6f42c1 100%);
                color: white; 
                padding: 30px; 
                border-radius: 10px; 
                text-align: center; 
                margin-bottom: 30px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .stat-number {{
                font-size: 2.5em;
                font-weight: bold;
                color: #17a2b8;
                margin-bottom: 10px;
            }}
            .translation-table {{
                background: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                margin-bottom: 30px;
            }}
            .table-header {{
                background: #343a40;
                color: white;
                padding: 20px;
                font-weight: bold;
            }}
            .translation-row {{
                padding: 15px 20px;
                border-bottom: 1px solid #e9ecef;
                display: grid;
                grid-template-columns: 1fr 1fr 100px 150px 120px;
                gap: 15px;
                align-items: center;
            }}
            .translation-row:nth-child(even) {{
                background: #f8f9fa;
            }}
            .status-badge {{
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.85em;
                font-weight: bold;
                text-align: center;
            }}
            .status-pending {{ background: #fff3cd; color: #856404; }}
            .status-inprogress {{ background: #d1ecf1; color: #0c5460; }}
            .status-succeeded {{ background: #d4edda; color: #155724; }}
            .status-failed {{ background: #f8d7da; color: #721c24; }}
            .empty-state {{
                text-align: center;
                padding: 60px 20px;
                color: #6c757d;
            }}
            .empty-icon {{
                font-size: 4em;
                margin-bottom: 20px;
                opacity: 0.5;
            }}
            .nav-links {{
                text-align: center;
                margin: 30px 0;
            }}
            .nav-links a {{
                display: inline-block;
                margin: 0 10px;
                padding: 12px 24px;
                background: #6c757d;
                color: white;
                text-decoration: none;
                border-radius: 25px;
                transition: all 0.3s;
            }}
            .nav-links a:hover {{
                background: #495057;
                transform: translateY(-2px);
            }}
            .refresh-note {{
                text-align: center;
                color: #6c757d;
                margin-top: 20px;
                font-size: 0.9em;
            }}
            .timestamp {{
                font-family: monospace;
                font-size: 0.8em;
                color: #6c757d;
            }}
        </style>
        <script>
            // Auto-refresh toutes les 10 secondes
            setTimeout(() => location.reload(), 10000);
        </script>
    </head>
    <body>
        <div class="header">
            <h1>📊 Traductions Actives</h1>
            <p>Surveillance en temps réel des traductions</p>
            <p class="timestamp">Dernière mise à jour: {current_time} UTC</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_translations}</div>
                <div>Traductions Totales</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{status_counts.get('En cours', 0)}</div>
                <div>En Cours</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{status_counts.get('Succeeded', 0)}</div>
                <div>Réussies</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{status_counts.get('Failed', 0)}</div>
                <div>Échouées</div>
            </div>
        </div>
        
        {translations_html}
        
        <div class="nav-links">
            <a href="/">🏠 Accueil</a>
            <a href="/health">🔍 Santé</a>
            <a href="/tools">🛠️ Outils</a>
        </div>
        
        <div class="refresh-note">
            🔄 Cette page se rafraîchit automatiquement toutes les 10 secondes
        </div>
        
        <div class="translation-table">
            <div class="table-header">
                💡 Commandes utiles
            </div>
            <div style="padding: 20px;">
                <p><strong>Démarrer une traduction:</strong></p>
                <code>POST /translate</code> avec les paramètres JSON
                
                <p style="margin-top: 15px;"><strong>Vérifier le statut:</strong></p>
                <code>GET /status/{{translation_id}}</code>
                
                <p style="margin-top: 15px;"><strong>Récupérer le résultat:</strong></p>
                <code>GET /result/{{translation_id}}</code>
            </div>
        </div>
    </body>
    </html>
    """

    return web.Response(text=html_content, content_type='text/html')


@routes.get('/')
async def home_page(request: Request) -> Response:
    """Page d'accueil du serveur de traduction"""

    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Serveur MCP de Traduction</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 800px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }
            .header { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
                padding: 30px; 
                border-radius: 10px; 
                text-align: center; 
                margin-bottom: 30px;
            }
            .card { 
                background: white; 
                padding: 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
                margin-bottom: 20px;
            }
            .endpoint { 
                background: #f8f9fa; 
                padding: 10px; 
                border-radius: 5px; 
                margin: 5px 0; 
                font-family: monospace;
            }
            .method-get { color: #28a745; font-weight: bold; }
            .method-post { color: #007bff; font-weight: bold; }
            .status-online { color: #28a745; }
            .emoji { font-size: 1.2em; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🌍 Serveur MCP de Traduction</h1>
            <p>Service de traduction de documents pour Copilot Studio</p>
            <p class="status-online">● En ligne</p>
        </div>
        
        <div class="card">
            <h2>📋 Endpoints disponibles</h2>
            <div class="endpoint"><span class="method-get">GET</span> /health - Vérification de santé</div>
            <div class="endpoint"><span class="method-get">GET</span> /tools - Liste des outils MCP</div>
            <div class="endpoint"><span class="method-post">POST</span> /translate - Lancer une traduction</div>
            <div class="endpoint"><span class="method-get">GET</span> /status/{id} - Vérifier le statut</div>
            <div class="endpoint"><span class="method-get">GET</span> /result/{id} - Récupérer le résultat</div>
            <div class="endpoint"><span class="method-get">GET</span> /translations - Traductions actives</div>
        </div>
        
        <div class="card">
            <h2>🛠️ Outils MCP</h2>
            <p><strong>translate_document</strong> - Traduit un document vers une langue cible</p>
            <p><strong>check_translation_status</strong> - Vérifie l'état d'une traduction</p>
            <p><strong>get_translation_result</strong> - Récupère le document traduit</p>
        </div>
        
        <div class="card">
            <h2>🚀 Utilisation</h2>
            <p>Ce serveur est conçu pour être utilisé avec <strong>Copilot Studio</strong> via des webhooks HTTP.</p>
            <p>Configurez l'URL du webhook sur : <code>http://localhost:3000</code></p>
        </div>
        
        <div class="card">
            <h2>🧪 Tests rapides</h2>
            <p><a href="/health" target="_blank">🔍 Vérifier la santé du serveur</a></p>
            <p><a href="/tools" target="_blank">🛠️ Voir les outils disponibles</a></p>
            <p><a href="/translations" target="_blank">📊 Voir les traductions actives</a></p>
        </div>
        
        <div class="card">
            <h2>📚 Documentation</h2>
            <p>Format des données :</p>
            <ul>
                <li><strong>file_content</strong> : Contenu du fichier en base64</li>
                <li><strong>file_name</strong> : Nom du fichier avec extension</li>
                <li><strong>target_language</strong> : Code langue (fr, en, es, de, etc.)</li>
                <li><strong>user_id</strong> : Identifiant unique de l'utilisateur</li>
            </ul>
        </div>
    </body>
    </html>
    """

    return web.Response(text=html_content, content_type='text/html')


@routes.get('/favicon.ico')
async def favicon(request: Request) -> Response:
    """Favicon simple pour éviter les erreurs 404"""
    # Retourne un favicon vide (1x1 pixel transparent)
    favicon_data = b'\x00\x00\x01\x00\x01\x00\x01\x01\x00\x00\x01\x00\x18\x00(\x00\x00\x00\x16\x00\x00\x00(\x00\x00\x00\x01\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    return web.Response(body=favicon_data, content_type='image/x-icon')


@routes.get('/mcp')
@routes.post('/mcp')
async def mcp_endpoint(request: Request) -> Response:
    """Endpoint MCP pour VS Code et autres clients MCP"""

    try:
        if request.method == 'GET':
            # Réponse pour les requêtes GET (connexion initiale)
            return web.json_response({
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "translation-mcp-server",
                        "version": "1.0.0"
                    }
                }
            })

        elif request.method == 'POST':
            # Traitement des requêtes JSON-RPC MCP
            data = await request.json()

            # Validation du format JSON-RPC
            if "jsonrpc" not in data or data["jsonrpc"] != "2.0":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request"
                    }
                }, status=400)

            method = data.get("method")
            params = data.get("params", {})
            request_id = data.get("id")

            logger.info(f"🔄 Requête MCP: {method}")

            # Traitement des méthodes MCP
            if method == "initialize":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "translation-mcp-server",
                            "version": "1.0.0"
                        }
                    }
                })

            elif method == "tools/list":
                tools = [
                    {
                        "name": "translate_document",
                        "description": "Traduit un document vers une langue cible",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_content": {"type": "string", "description": "Contenu du fichier en base64"},
                                "file_name": {"type": "string", "description": "Nom du fichier"},
                                "target_language": {"type": "string", "description": "Langue cible"},
                                "user_id": {"type": "string", "description": "ID utilisateur"}
                            },
                            "required": ["file_content", "file_name", "target_language", "user_id"]
                        }
                    },
                    {
                        "name": "check_translation_status",
                        "description": "Vérifie l'état d'une traduction",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "translation_id": {"type": "string", "description": "ID de la traduction"}
                            },
                            "required": ["translation_id"]
                        }
                    },
                    {
                        "name": "get_translation_result",
                        "description": "Récupère le résultat d'une traduction",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "translation_id": {"type": "string", "description": "ID de la traduction"},
                                "save_to_onedrive": {"type": "boolean", "description": "Sauvegarder sur OneDrive"}
                            },
                            "required": ["translation_id"]
                        }
                    }
                ]

                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": tools
                    }
                })

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_arguments = params.get("arguments", {})

                logger.info(f"🛠️ Appel outil MCP: {tool_name}")

                # Redirection vers nos endpoints REST existants
                if tool_name == "translate_document":
                    # Simuler un appel à notre endpoint /translate
                    try:
                        blob_service = BlobService()
                        translation_service = TranslationService()

                        # Préparation des blobs
                        blob_urls = await blob_service.prepare_blobs(
                            file_content_base64=tool_arguments["file_content"],
                            file_name=tool_arguments["file_name"],
                            target_language=tool_arguments["target_language"]
                        )

                        # Démarrage de la traduction
                        translation_id = await translation_service.start_translation(
                            source_url=blob_urls["source_url"],
                            target_url=blob_urls["target_url"],
                            target_language=tool_arguments["target_language"]
                        )

                        # Stockage des informations
                        active_translations[translation_id] = {
                            "file_name": tool_arguments["file_name"],
                            "target_language": tool_arguments["target_language"],
                            "user_id": tool_arguments["user_id"],
                            "blob_urls": blob_urls,
                            "status": "En cours",
                            "started_at": asyncio.get_event_loop().time()
                        }

                        return web.json_response({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"✅ Traduction démarrée avec succès!\n\n📄 Fichier: {tool_arguments['file_name']}\n🌍 Langue cible: {tool_arguments['target_language']}\n🆔 ID de traduction: {translation_id}\n\n💡 Utilisez 'check_translation_status' pour suivre l'avancement."
                                    }
                                ]
                            }
                        })

                    except Exception as e:
                        return web.json_response({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32603,
                                "message": f"Erreur lors de la traduction: {str(e)}"
                            }
                        })

                elif tool_name == "check_translation_status":
                    translation_id = tool_arguments.get("translation_id")

                    if translation_id not in active_translations:
                        return web.json_response({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"❌ Traduction '{translation_id}' non trouvée"
                                    }
                                ]
                            }
                        })

                    try:
                        translation_service = TranslationService()
                        status = await translation_service.check_translation_status(translation_id)

                        translation_info = active_translations[translation_id]

                        if status["status"] == "Succeeded":
                            message = f"✅ Traduction terminée avec succès!\n\n📄 Fichier: {translation_info['file_name']}\n🌍 Langue: {translation_info['target_language']}\n🆔 ID: {translation_id}\n\n💡 Utilisez 'get_translation_result' pour récupérer le document traduit."
                        elif status["status"] == "Failed":
                            message = f"❌ Traduction échouée\n\n📄 Fichier: {translation_info['file_name']}\n🆔 ID: {translation_id}\n🚨 Erreur: {status.get('error', 'Erreur inconnue')}"
                        else:
                            message = f"⏳ Traduction en cours...\n\n📄 Fichier: {translation_info['file_name']}\n🌍 Langue: {translation_info['target_language']}\n🆔 ID: {translation_id}\n📊 Statut: {status.get('progress', 'En cours...')}"

                        return web.json_response({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": message
                                    }
                                ]
                            }
                        })

                    except Exception as e:
                        return web.json_response({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32603,
                                "message": f"Erreur lors de la vérification: {str(e)}"
                            }
                        })

                else:
                    return web.json_response({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"Outil non trouvé: {tool_name}"
                        }
                    })

            else:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Méthode non supportée: {method}"
                    }
                })

    except Exception as e:
        logger.error(f"❌ Erreur MCP: {str(e)}")
        return web.json_response({
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": f"Erreur interne: {str(e)}"
            }
        }, status=500)


@routes.get('/files')
async def list_files(request: Request) -> Response:
    """Liste les fichiers disponibles dans le container doc-to-trad"""

    try:
        # Paramètre optionnel pour filtrer par extension
        filter_extension = request.query.get('extension', None)

        blob_service = BlobService()
        files = await blob_service.list_input_files(filter_extension)

        return web.json_response({
            "success": True,
            "files": files,
            "count": len(files),
            "container": blob_service.input_container,
            "filter_extension": filter_extension
        })

    except Exception as e:
        logger.error(f"❌ Erreur liste fichiers: {str(e)}")
        return web.json_response({
            "success": False,
            "error": f"Erreur lors de la récupération des fichiers: {str(e)}"
        }, status=500)


@routes.get('/output-files')
async def list_output_files(request: Request) -> Response:
    """Liste les fichiers traduits dans le container doc-trad avec leurs URLs"""

    try:
        # Paramètre optionnel pour filtrer par extension
        filter_extension = request.query.get('extension', None)

        blob_service = BlobService()
        files = blob_service.list_output_files(filter_extension)

        return web.json_response({
            "success": True,
            "files": files,
            "count": len(files),
            "container": blob_service.output_container,
            "filter_extension": filter_extension
        })

    except Exception as e:
        logger.error(f"❌ Erreur liste fichiers de sortie: {str(e)}")
        return web.json_response({
            "success": False,
            "error": f"Erreur lors de la récupération des fichiers de sortie: {str(e)}"
        }, status=500)


@routes.get('/output-files/{blob_name}/url')
async def get_output_file_url(request: Request) -> Response:
    """Génère une URL SAS pour télécharger un fichier traduit"""

    try:
        blob_name = request.match_info['blob_name']
        expires_in_hours = int(request.query.get('expires_in_hours', 24))

        blob_service = BlobService()
        url = await blob_service.get_output_file_url(blob_name, expires_in_hours)

        if url:
            return web.json_response({
                "success": True,
                "url": url,
                "blob_name": blob_name,
                "expires_in_hours": expires_in_hours
            })
        else:
            return web.json_response({
                "success": False,
                "error": "Fichier non trouvé ou erreur lors de la génération de l'URL"
            }), 404

    except Exception as e:
        logger.error(f"❌ Erreur génération URL: {str(e)}")
        return web.json_response({
            "success": False,
            "error": str(e)
        }), 500


@routes.get('/openapi.yaml')
async def get_openapi_spec(request: Request) -> Response:
    """Retourne la spécification OpenAPI 3.0"""

    try:
        # Lecture du fichier OpenAPI
        import yaml
        with open('openapi-3.0.yaml', 'r', encoding='utf-8') as f:
            openapi_content = f.read()

        return web.Response(
            text=openapi_content,
            content_type='application/x-yaml',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
    except Exception as e:
        return web.json_response({
            "error": f"Erreur lors de la lecture du fichier OpenAPI: {str(e)}"
        }, status=500)


@routes.get('/swagger.yaml')
async def get_swagger_spec(request: Request) -> Response:
    """Retourne la spécification Swagger 2.0 pour compatibilité"""

    try:
        # Lecture du fichier Swagger
        with open('swagger_updated.yaml', 'r', encoding='utf-8') as f:
            swagger_content = f.read()

        return web.Response(
            text=swagger_content,
            content_type='application/x-yaml',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
    except Exception as e:
        return web.json_response({
            "error": f"Erreur lors de la lecture du fichier Swagger: {str(e)}"
        }, status=500)


async def create_app() -> web.Application:
    """Création de l'application web"""

    app = web.Application()
    app.add_routes(routes)

    # Configuration CORS pour Copilot Studio
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })

    # Ajouter CORS à toutes les routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app


async def main():
    """Point d'entrée principal"""

    logger.info("🚀 Démarrage du serveur API de traduction...")

    # Validation de la configuration
    errors = Config.validate()
    if errors:
        logger.error("❌ Erreurs de configuration:")
        for error in errors:
            logger.error(f"   - {error}")
        return

    logger.info("✅ Configuration validée")

    # Création de l'application
    app = await create_app()

    # Démarrage du serveur
    runner = web.AppRunner(app)
    await runner.setup()

    port = Config.MCP_SERVER_PORT
    # Écouter sur toutes les interfaces pour Azure Container Apps
    host = '0.0.0.0'
    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"🌟 Serveur démarré sur http://{host}:{port}")
    logger.info("📋 Endpoints disponibles:")
    logger.info("   GET  /health              - Vérification de santé")
    logger.info("   GET  /tools               - Liste des outils")
    logger.info("   POST /translate           - Lancer une traduction")
    logger.info("   GET  /status/{id}         - Vérifier le statut")
    logger.info("   GET  /result/{id}         - Récupérer le résultat")
    logger.info("   GET  /translations        - Traductions actives")
    logger.info("   POST /mcp                 - Endpoint MCP (VS Code)")
    logger.info("\n💡 Utilisez Ctrl+C pour arrêter le serveur")

    try:
        # Maintenir le serveur en vie
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("⏹️ Arrêt du serveur...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
