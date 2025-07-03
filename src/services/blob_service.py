"""
Service de gestion des blobs Azure Storage
Adapté de la logique Azure Functions existante
"""

import logging
import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BlobService:
    """Service pour la gestion des blobs Azure Storage"""

    def __init__(self):
        # Configuration Azure Storage
        self.account_name = os.getenv('AZURE_ACCOUNT_NAME')
        self.account_key = os.getenv('AZURE_ACCOUNT_KEY')

        if not self.account_key.endswith("=="):
            self.account_key += "=="

        # Noms des conteneurs
        self.input_container = "doc-to-trad"
        self.output_container = "doc-trad"

        # Client Blob Storage
        self.blob_service_client = BlobServiceClient(
            account_url=f"https://{self.account_name}.blob.core.windows.net",
            credential=self.account_key
        )

        logger.info("✅ BlobService initialisé")

    async def prepare_blobs(self, file_content_base64: str, file_name: str, target_language: str) -> Dict[str, str]:
        """
        Prépare les blobs source et cible pour la traduction
        Équivalent de la fonction prepare_blobs d'Azure Functions
        """

        logger.info(
            f"🔄 Préparation des blobs pour {file_name} → {target_language}")

        try:
            # Normalisation des noms de fichiers pour Azure Storage
            normalized_file_name = self._normalize_blob_name(file_name)

            # Génération des noms de fichiers avec suffixe de langue amélioré
            input_blob_name = normalized_file_name
            file_base, file_ext = normalized_file_name.rsplit(
                ".", 1) if "." in normalized_file_name else (normalized_file_name, "")

            # Format amélioré: file_name-fr.docx au lieu de file_name_fr.docx
            output_blob_name = f"{file_base}-{target_language}.{file_ext}" if file_ext else f"{file_base}-{target_language}"

            logger.info(f"📄 Fichier source: {input_blob_name}")
            logger.info(f"📄 Fichier cible: {output_blob_name}")

            # Nettoyage des anciens fichiers (>1h)
            await self._delete_old_files(self.output_container, max_age_hours=1)

            # Suppression du fichier cible s'il existe déjà
            await self._check_and_delete_target_blob(self.output_container, output_blob_name)

            # Conversion et upload du fichier source
            file_content_binary = base64.b64decode(file_content_base64)

            input_blob_client = self.blob_service_client.get_blob_client(
                container=self.input_container,
                blob=input_blob_name
            )
            input_blob_client.upload_blob(file_content_binary, overwrite=True)
            logger.info("✅ Fichier source uploadé")

            # Génération des SAS URLs
            source_url = self._generate_sas_url(
                self.input_container, input_blob_name, permissions="r")
            target_url = self._generate_sas_url(
                self.output_container, output_blob_name, permissions="rw")

            logger.info("✅ URLs SAS générées")

            return {
                "source_url": source_url,
                "target_url": target_url,
                "input_blob_name": input_blob_name,
                "output_blob_name": output_blob_name,
                "original_file_name": file_name,
                "normalized_file_name": normalized_file_name
            }

        except Exception as e:
            logger.error(
                f"❌ Erreur lors de la préparation des blobs: {str(e)}")
            raise

    async def download_translated_file(self, target_url: str) -> bytes:
        """Télécharge le fichier traduit depuis le blob storage"""

        try:
            # Extraction du nom du blob depuis l'URL
            # Format: https://account.blob.core.windows.net/container/blob?sas
            url_parts = target_url.split('/')
            container_name = url_parts[-2]
            blob_name_with_sas = url_parts[-1]
            blob_name = blob_name_with_sas.split('?')[0]

            logger.info(f"📥 Téléchargement du fichier: {blob_name}")

            blob_client = self.blob_service_client.get_blob_client(
                container=container_name,
                blob=blob_name
            )

            if not blob_client.exists():
                raise FileNotFoundError(
                    f"Le fichier traduit {blob_name} n'existe pas dans le conteneur {container_name}")

            download_stream = blob_client.download_blob()
            content = download_stream.readall()

            logger.info(f"✅ Fichier traduit téléchargé: {len(content)} bytes")
            return content

        except Exception as e:
            logger.error(f"❌ Erreur lors du téléchargement: {str(e)}")
            # Log plus détaillé pour déboguer
            if 'InvalidResourceName' in str(e):
                logger.error(f"🔍 URL problématique: {target_url}")
                logger.error(
                    f"🔍 Container: {container_name if 'container_name' in locals() else 'N/A'}")
                logger.error(
                    f"🔍 Blob: {blob_name if 'blob_name' in locals() else 'N/A'}")
            raise Exception(f"Erreur lors de la récupération: {str(e)}")

    def _generate_sas_url(self, container_name: str, blob_name: str, permissions: str = "r") -> str:
        """Génère une URL SAS pour un blob"""

        # Configuration des permissions
        perm_map = {
            "r": BlobSasPermissions(read=True),
            "w": BlobSasPermissions(write=True),
            "rw": BlobSasPermissions(read=True, write=True)
        }

        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=self.account_key,
            permission=perm_map.get(
                permissions, BlobSasPermissions(read=True)),
            expiry=datetime.utcnow() + timedelta(hours=2)  # 2h de validité
        )

        blob_client = self.blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_name
        )

        return f"{blob_client.url}?{sas_token}"

    async def _delete_old_files(self, container_name: str, max_age_hours: int = 1):
        """Supprime les fichiers anciens du conteneur"""

        try:
            container_client = self.blob_service_client.get_container_client(
                container_name)
            blob_list = container_client.list_blobs()
            cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - \
                timedelta(hours=max_age_hours)

            deleted_count = 0
            for blob in blob_list:
                if blob.last_modified < cutoff_time:
                    container_client.delete_blob(blob.name)
                    deleted_count += 1
                    logger.info(f"🗑️ Fichier supprimé: {blob.name}")

            if deleted_count > 0:
                logger.info(
                    f"✅ {deleted_count} ancien(s) fichier(s) supprimé(s)")

        except Exception as e:
            logger.warning(f"⚠️ Erreur lors du nettoyage: {str(e)}")

    async def _check_and_delete_target_blob(self, container_name: str, blob_name: str):
        """Supprime le fichier cible s'il existe pour éviter les conflits"""

        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=container_name,
                blob=blob_name
            )

            if blob_client.exists():
                blob_client.delete_blob()
                logger.info(f"🗑️ Fichier cible existant supprimé: {blob_name}")

        except Exception as e:
            logger.warning(f"⚠️ Erreur lors de la suppression: {str(e)}")

    async def check_blob_exists(self, container: str, blob_name: str) -> bool:
        """Vérifie si un blob existe dans un container"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=container,
                blob=blob_name
            )
            return blob_client.exists()
        except Exception as e:
            logger.error(
                f"Erreur lors de la vérification du blob {blob_name}: {str(e)}")
            return False

    async def prepare_translation_urls(self, input_blob_name: str, target_language: str) -> Dict[str, str]:
        """
        Prépare les URLs pour la traduction d'un blob existant
        Le fichier source est déjà dans le container doc-to-trad
        """

        logger.info(
            f"🔄 Préparation des URLs pour {input_blob_name} → {target_language}")

        try:
            # Génération du nom du fichier de sortie
            file_base, file_ext = input_blob_name.rsplit(
                ".", 1) if "." in input_blob_name else (input_blob_name, "")

            # Format: file_name-fr.docx
            output_blob_name = f"{file_base}-{target_language}.{file_ext}" if file_ext else f"{file_base}-{target_language}"

            logger.info(f"📄 Fichier source: {input_blob_name}")
            logger.info(f"📄 Fichier cible: {output_blob_name}")

            # Nettoyage des anciens fichiers (>1h)
            await self._delete_old_files(self.output_container, max_age_hours=1)

            # Suppression du fichier cible s'il existe déjà
            await self._check_and_delete_target_blob(self.output_container, output_blob_name)

            # Génération des SAS URLs
            source_url = self._generate_sas_url(
                self.input_container, input_blob_name, permissions="r")
            target_url = self._generate_sas_url(
                self.output_container, output_blob_name, permissions="rw")

            logger.info("✅ URLs SAS générées")

            return {
                "source_url": source_url,
                "target_url": target_url,
                "input_blob_name": input_blob_name,
                "output_blob_name": output_blob_name,
                "original_file_name": input_blob_name,
                "normalized_file_name": input_blob_name
            }

        except Exception as e:
            logger.error(f"Erreur lors de la préparation des URLs: {str(e)}")
            raise

    def _normalize_blob_name(self, file_name: str) -> str:
        """
        Normalise un nom de fichier pour être compatible avec Azure Storage
        - Remplace les espaces par des underscores
        - Remplace les caractères spéciaux par des underscores
        - Supprime les caractères consécutifs d'underscores
        """
        import re

        # Remplacer les espaces et tirets par des underscores
        normalized = file_name.replace(' ', '_').replace('-', '_')

        # Garder seulement les caractères alphanumériques, points et underscores
        normalized = re.sub(r'[^a-zA-Z0-9._]', '_', normalized)

        # Supprimer les underscores consécutifs
        normalized = re.sub(r'_+', '_', normalized)

        # Supprimer les underscores en début et fin
        normalized = normalized.strip('_')

        # Limiter la longueur (garder extension si présente)
        max_length = 200  # Limite conservatrice pour éviter les problèmes
        if len(normalized) > max_length:
            if '.' in normalized:
                name_part, ext = normalized.rsplit('.', 1)
                max_name_length = max_length - len(ext) - 1  # -1 pour le point
                normalized = name_part[:max_name_length] + '.' + ext
            else:
                normalized = normalized[:max_length]

            logger.warning(
                f"⚠️ Nom de fichier tronqué: {file_name} → {normalized}")

        logger.info(f"📝 Nom normalisé: '{file_name}' → '{normalized}'")
        return normalized

    async def list_input_files(self, filter_extension: str = None) -> List[str]:
        """Liste les fichiers dans le container d'entrée"""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.input_container
            )

            files = []
            # Utilisation de la méthode synchrone avec list_blobs()
            for blob in container_client.list_blobs():
                blob_name = blob.name

                # Filtrage par extension si spécifié
                if filter_extension:
                    if not blob_name.lower().endswith(f".{filter_extension.lower()}"):
                        continue

                files.append(blob_name)

            return sorted(files)  # Tri alphabétique

        except Exception as e:
            logger.error(f"Erreur lors de la liste des fichiers: {str(e)}")
            return []

    def list_output_files(self, filter_extension: str = None) -> List[Dict[str, Any]]:
        """Liste les fichiers dans le container de sortie (doc-trad) avec leurs URLs"""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.output_container
            )

            files = []
            # Utilisation de la méthode synchrone avec list_blobs()
            for blob in container_client.list_blobs():
                blob_name = blob.name

                # Filtrage par extension si spécifié
                if filter_extension:
                    if not blob_name.lower().endswith(f".{filter_extension.lower()}"):
                        continue

                # Génération de l'URL SAS pour le fichier
                try:
                    sas_url = self._generate_sas_url(
                        self.output_container, blob_name, permissions="r")

                    files.append({
                        "name": blob_name,
                        "size": blob.size,
                        "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
                        "url": sas_url,
                        "content_type": blob.content_settings.content_type if blob.content_settings else None
                    })
                except Exception as url_error:
                    logger.error(
                        f"Erreur génération URL pour {blob_name}: {str(url_error)}")
                    files.append({
                        "name": blob_name,
                        "size": blob.size,
                        "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
                        "url": None,
                        "error": str(url_error)
                    })

            return sorted(files, key=lambda x: x["name"])  # Tri alphabétique

        except Exception as e:
            logger.error(
                f"Erreur lors de la liste des fichiers de sortie: {str(e)}")
            return []

    def get_output_file_url(self, blob_name, expires_in_hours=24):
        """
        Génère une URL SAS pour un fichier dans le container de sortie (doc-trad)
        """
        try:
            container_client = self.blob_service_client.get_container_client(
                "doc-trad")
            blob_client = container_client.get_blob_client(blob_name)

            # Vérifier si le blob existe
            if not blob_client.exists():
                return None

            # Générer l'URL SAS
            sas_token = generate_blob_sas(
                account_name=self.account_name,
                container_name="doc-trad",
                blob_name=blob_name,
                account_key=self.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=expires_in_hours)
            )

            url = f"https://{self.account_name}.blob.core.windows.net/doc-trad/{blob_name}?{sas_token}"
            return url

        except Exception as e:
            print(
                f"Erreur lors de la génération de l'URL pour {blob_name}: {e}")
            return None
