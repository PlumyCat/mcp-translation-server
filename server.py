#!/usr/bin/env python3
"""
Serveur MCP pour la traduction de documents
Basé sur la logique Azure Functions existante
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    InitializeResult,
    ServerCapabilities
)

from src.services.blob_service import BlobService
from src.services.translation_service import TranslationService
from src.services.graph_service import GraphService
from src.models.schemas import TranslationRequest, TranslationStatus

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TranslationMCPServer:
    """Serveur MCP pour la traduction de documents"""

    def __init__(self):
        self.server = Server("translation-mcp-server")
        self.blob_service = BlobService()
        self.translation_service = TranslationService()
        self.graph_service = GraphService()

        # Stockage des traductions en cours
        self.active_translations: Dict[str, Dict[str, Any]] = {}

        self._setup_handlers()

    def _setup_handlers(self):
        """Configuration des handlers MCP"""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """Liste des outils disponibles"""
            return [
                Tool(
                    name="translate_document",
                    description="Lance la traduction d'un document déjà uploadé dans le container doc-to-trad. Le fichier doit être préalablement déposé via Copilot.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "blob_name": {
                                "type": "string",
                                "description": "Nom du blob/fichier dans le container doc-to-trad (avec extension)"
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
                        "required": ["blob_name", "target_language", "user_id"]
                    }
                ),
                Tool(
                    name="check_translation_status",
                    description="Vérifie l'état d'une traduction en cours et retourne le statut actuel.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "translation_id": {
                                "type": "string",
                                "description": "ID de la traduction à vérifier"
                            }
                        },
                        "required": ["translation_id"]
                    }
                ),
                Tool(
                    name="get_translation_result",
                    description="Récupère le document traduit et l'enregistre sur OneDrive de l'utilisateur.",
                    inputSchema={
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
                ),
                Tool(
                    name="list_available_files",
                    description="Liste les fichiers disponibles dans le container doc-to-trad pour traduction.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "filter_extension": {
                                "type": "string",
                                "description": "Filtrer par extension de fichier (ex: 'pdf', 'docx', 'txt'). Optionnel."
                            }
                        },
                        "required": []
                    }
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Exécution des outils"""

            try:
                if name == "translate_document":
                    return await self._handle_translate_document(arguments)
                elif name == "list_available_files":
                    return await self._handle_list_files(arguments)
                elif name == "check_translation_status":
                    return await self._handle_check_status(arguments)
                elif name == "get_translation_result":
                    return await self._handle_get_result(arguments)
                else:
                    return [TextContent(
                        type="text",
                        text=f"❌ Outil '{name}' non reconnu"
                    )]

            except Exception as e:
                logger.error(f"Erreur lors de l'exécution de {name}: {str(e)}")
                return [TextContent(
                    type="text",
                    text=f"❌ Erreur: {str(e)}"
                )]

    async def _handle_translate_document(self, args: Dict[str, Any]) -> List[TextContent]:
        """Lance une traduction de document à partir d'un blob existant"""

        try:
            # Validation des arguments
            blob_name = args["blob_name"]
            target_language = args["target_language"]
            user_id = args["user_id"]

            logger.info(
                f"🚀 Démarrage traduction: {blob_name} → {target_language}")

            # Étape 1: Vérification de l'existence du blob
            blob_exists = await self.blob_service.check_blob_exists(
                container=self.blob_service.input_container,
                blob_name=blob_name
            )

            if not blob_exists:
                return [TextContent(
                    type="text",
                    text=f"❌ Fichier '{blob_name}' non trouvé dans le container {self.blob_service.input_container}"
                )]

            # Étape 2: Préparation des URLs pour la traduction
            blob_urls = await self.blob_service.prepare_translation_urls(
                input_blob_name=blob_name,
                target_language=target_language
            )

            # Étape 3: Démarrage de la traduction
            translation_id = await self.translation_service.start_translation(
                source_url=blob_urls["source_url"],
                target_url=blob_urls["target_url"],
                target_language=target_language
            )

            # Stockage des informations de traduction
            self.active_translations[translation_id] = {
                "blob_name": blob_name,
                "target_language": target_language,
                "user_id": user_id,
                "blob_urls": blob_urls,
                "status": "En cours",
                "started_at": asyncio.get_event_loop().time()
            }

            return [TextContent(
                type="text",
                text=f"✅ Traduction démarrée avec succès!\n\n"
                     f"📄 Fichier: {blob_name}\n"
                     f"🌍 Langue cible: {target_language}\n"
                     f"🆔 ID de traduction: {translation_id}\n\n"
                     f"💡 Utilisez 'check_translation_status' avec cet ID pour suivre l'avancement."
            )]

        except Exception as e:
            logger.error(
                f"Erreur lors du démarrage de la traduction: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Erreur lors du démarrage de la traduction: {str(e)}"
            )]

    async def _handle_check_status(self, args: Dict[str, Any]) -> List[TextContent]:
        """Vérifie le statut d'une traduction"""

        try:
            translation_id = args["translation_id"]

            if translation_id not in self.active_translations:
                return [TextContent(
                    type="text",
                    text=f"❌ Traduction '{translation_id}' non trouvée"
                )]

            # Vérification du statut via l'API Azure Translator
            status = await self.translation_service.check_translation_status(translation_id)

            # Mise à jour du statut local
            self.active_translations[translation_id]["status"] = status["status"]

            translation_info = self.active_translations[translation_id]
            file_name = translation_info["file_name"]
            target_language = translation_info["target_language"]

            if status["status"] == "Succeeded":
                return [TextContent(
                    type="text",
                    text=f"✅ Traduction terminée avec succès!\n\n"
                         f"📄 Fichier: {file_name}\n"
                         f"🌍 Langue: {target_language}\n"
                         f"🆔 ID: {translation_id}\n\n"
                         f"💡 Utilisez 'get_translation_result' pour récupérer le document traduit."
                )]
            elif status["status"] == "Failed":
                error_msg = status.get("error", "Erreur inconnue")
                return [TextContent(
                    type="text",
                    text=f"❌ Traduction échouée\n\n"
                         f"📄 Fichier: {file_name}\n"
                         f"🆔 ID: {translation_id}\n"
                         f"🚨 Erreur: {error_msg}"
                )]
            else:
                progress = status.get("progress", "En cours...")
                return [TextContent(
                    type="text",
                    text=f"⏳ Traduction en cours...\n\n"
                         f"📄 Fichier: {file_name}\n"
                         f"🌍 Langue: {target_language}\n"
                         f"🆔 ID: {translation_id}\n"
                         f"📊 Statut: {progress}"
                )]

        except Exception as e:
            logger.error(f"Erreur lors de la vérification du statut: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Erreur lors de la vérification: {str(e)}"
            )]

    async def _handle_get_result(self, args: Dict[str, Any]) -> List[TextContent]:
        """Récupère le résultat de la traduction"""

        try:
            translation_id = args["translation_id"]
            save_to_onedrive = args.get("save_to_onedrive", True)

            if translation_id not in self.active_translations:
                return [TextContent(
                    type="text",
                    text=f"❌ Traduction '{translation_id}' non trouvée"
                )]

            translation_info = self.active_translations[translation_id]

            # Vérification que la traduction est terminée
            status = await self.translation_service.check_translation_status(translation_id)
            if status["status"] != "Succeeded":
                return [TextContent(
                    type="text",
                    text=f"⚠️ La traduction n'est pas encore terminée (statut: {status['status']})"
                )]

            # Téléchargement du fichier traduit
            translated_content = await self.blob_service.download_translated_file(
                translation_info["blob_urls"]["target_url"]
            )

            result_message = f"✅ Document traduit récupéré avec succès!\n\n"
            result_message += f"📄 Fichier original: {translation_info['file_name']}\n"
            result_message += f"🌍 Langue: {translation_info['target_language']}\n"
            result_message += f"📁 Taille: {len(translated_content)} bytes\n"

            # Sauvegarde sur OneDrive si demandée
            if save_to_onedrive:
                try:
                    onedrive_url = await self.graph_service.save_to_onedrive(
                        user_id=translation_info["user_id"],
                        file_content=translated_content,
                        file_name=translation_info["file_name"],
                        target_language=translation_info["target_language"]
                    )
                    result_message += f"☁️ Sauvegardé sur OneDrive: {onedrive_url}\n"
                except Exception as e:
                    logger.warning(f"Erreur sauvegarde OneDrive: {str(e)}")
                    result_message += f"⚠️ Échec sauvegarde OneDrive: {str(e)}\n"

            # Nettoyage des données temporaires
            del self.active_translations[translation_id]

            return [TextContent(
                type="text",
                text=result_message
            )]

        except Exception as e:
            logger.error(
                f"Erreur lors de la récupération du résultat: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Erreur lors de la récupération: {str(e)}"
            )]

    async def _handle_list_files(self, args: Dict[str, Any]) -> List[TextContent]:
        """Liste les fichiers disponibles dans le container doc-to-trad"""

        try:
            filter_extension = args.get("filter_extension", None)

            # Récupération de la liste des blobs
            files = await self.blob_service.list_input_files(filter_extension)

            if not files:
                return [TextContent(
                    type="text",
                    text=f"📁 Aucun fichier trouvé dans le container {self.blob_service.input_container}"
                )]

            # Formatage de la liste
            files_list = "\n".join([f"📄 {file}" for file in files])

            return [TextContent(
                type="text",
                text=f"📁 Fichiers disponibles dans {self.blob_service.input_container}:\n\n{files_list}\n\n"
                     f"💡 Utilisez 'translate_document' avec le nom du fichier pour le traduire."
            )]

        except Exception as e:
            logger.error(f"Erreur lors de la liste des fichiers: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Erreur lors de la récupération des fichiers: {str(e)}"
            )]


async def main():
    """Point d'entrée principal du serveur MCP"""

    logger.info("🚀 Démarrage du serveur MCP de traduction...")

    # Création et démarrage du serveur
    mcp_server = TranslationMCPServer()

    # Configuration du transport (stdio pour MCP)
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        initialization_options = InitializeResult(
            protocolVersion="2024-11-05",
            capabilities=ServerCapabilities(
                tools={}
            ),
            serverInfo={
                "name": "translation-mcp-server",
                "version": "1.0.0"
            }
        )
        await mcp_server.server.run(
            read_stream,
            write_stream,
            initialization_options
        )

if __name__ == "__main__":
    asyncio.run(main())
