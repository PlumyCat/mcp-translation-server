"""
Service MS Graph pour l'intégration OneDrive
Adapté de la logique Azure Functions existante
"""

import logging
import os
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class GraphService:
    """Service pour l'intégration Microsoft Graph (OneDrive)"""

    def __init__(self):
        # Configuration Microsoft Graph
        self.client_id = os.getenv('CLIENT_ID')
        self.client_secret = os.getenv('SECRET_ID')
        self.tenant_id = os.getenv('TENANT_ID')
        self.onedrive_folder = os.getenv('ONEDRIVE_FOLDER')

        if not all([self.client_id, self.client_secret, self.tenant_id, self.onedrive_folder]):
            logger.warning(
                "⚠️ Configuration MS Graph incomplète - OneDrive non disponible")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("✅ GraphService initialisé")

        # URLs Graph API
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.graph_base_url = "https://graph.microsoft.com/v1.0"

        # Cache du token (simple, en production utiliser un cache plus robuste)
        self._access_token = None
        self._token_expires_at = 0

    async def save_to_onedrive(self, user_id: str, file_content: bytes, file_name: str, target_language: str) -> str:
        """
        Sauvegarde un fichier sur OneDrive de l'utilisateur
        Équivalent de download_and_upload_file d'Azure Functions
        """

        if not self.enabled:
            raise Exception("Service MS Graph non configuré")

        logger.info(f"☁️ Sauvegarde OneDrive pour utilisateur {user_id}")

        try:
            # Obtention du token d'accès
            access_token = await self._get_access_token()
            if not access_token:
                raise Exception(
                    "Impossible d'obtenir le token d'accès MS Graph")

            # Génération du nom de fichier avec suffixe de langue (format cohérent avec BlobService)
            file_base, file_ext = file_name.rsplit(
                ".", 1) if "." in file_name else (file_name, "")
            onedrive_file_name = f"{file_base}-{target_language}.{file_ext}" if file_ext else f"{file_base}-{target_language}"

            # Vérification et création du dossier onedrive_folder si nécessaire
            await self.create_documents_folder(user_id)

            # URL de destination sur OneDrive (dossier onedrive_folder)
            upload_url = f"{self.graph_base_url}/users/{user_id}/drive/root:/{self.onedrive_folder}/{onedrive_file_name}:/content"

            # Headers pour l'upload
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/octet-stream'
            }

            logger.info(f"📤 Upload vers OneDrive: {onedrive_file_name}")

            # Upload du fichier
            response = requests.put(
                upload_url,
                headers=headers,
                data=file_content,
                timeout=60  # Timeout plus long pour les gros fichiers
            )

            if response.status_code not in [200, 201]:
                logger.error(
                    f"❌ Erreur upload OneDrive: {response.status_code} - {response.text}")
                raise Exception(
                    f"Erreur upload OneDrive: {response.status_code}")

            # Récupération des informations du fichier uploadé
            file_info = response.json()
            onedrive_url = file_info.get('webUrl', 'URL non disponible')

            logger.info(
                f"✅ Fichier sauvegardé sur OneDrive: {onedrive_file_name}")
            logger.info(f"🔗 URL OneDrive: {onedrive_url}")

            return onedrive_url

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur réseau OneDrive: {str(e)}")
            raise Exception(f"Erreur réseau OneDrive: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde OneDrive: {str(e)}")
            raise

    async def _get_access_token(self) -> Optional[str]:
        """
        Obtient un token d'accès MS Graph
        Équivalent de get_access_token d'Azure Functions
        """

        try:
            logger.info("🔑 Obtention du token MS Graph...")

            # Headers et body pour la requête de token
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            body = {
                'client_id': self.client_id,
                'scope': 'https://graph.microsoft.com/.default',
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'
            }

            # Requête de token
            response = requests.post(
                self.token_url,
                headers=headers,
                data=body,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(
                    f"❌ Erreur token MS Graph: {response.status_code} - {response.text}")
                return None

            token_data = response.json()
            access_token = token_data.get('access_token')

            if access_token:
                logger.info("✅ Token MS Graph obtenu")
                # Cache simple du token (en production, gérer l'expiration)
                self._access_token = access_token
                return access_token
            else:
                logger.error("❌ Token non trouvé dans la réponse")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(
                f"❌ Erreur réseau lors de l'obtention du token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'obtention du token: {str(e)}")
            return None

    async def check_user_access(self, user_id: str) -> bool:
        """Vérifie si l'utilisateur est accessible via Graph API"""

        if not self.enabled:
            return False

        try:
            access_token = await self._get_access_token()
            if not access_token:
                return False

            # Test d'accès à l'utilisateur
            headers = {
                'Authorization': f'Bearer {access_token}'
            }

            response = requests.get(
                f"{self.graph_base_url}/users/{user_id}",
                headers=headers,
                timeout=15
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"❌ Erreur vérification utilisateur: {str(e)}")
            return False

    async def create_documents_folder(self, user_id: str) -> bool:
        """Crée le dossier self.onedrive_folder s'il n'existe pas"""

        if not self.enabled:
            return False

        try:
            access_token = await self._get_access_token()
            if not access_token:
                return False

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            # Vérification si le dossier existe
            folder_url = f"{self.graph_base_url}/users/{user_id}/drive/root:/{self.onedrive_folder}"
            response = requests.get(folder_url, headers=headers, timeout=15)

            if response.status_code == 200:
                logger.info(f"📁 Dossier {self.onedrive_folder} existe déjà")
                return True

            # Création du dossier
            create_url = f"{self.graph_base_url}/users/{user_id}/drive/root/children"
            folder_data = {
                "name": self.onedrive_folder,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename"
            }

            response = requests.post(
                create_url, headers=headers, json=folder_data, timeout=15)

            if response.status_code in [200, 201]:
                logger.info(f"✅ Dossier {self.onedrive_folder} créé")
                return True
            else:
                logger.error(
                    f"❌ Erreur création dossier: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Erreur création dossier: {str(e)}")
            return False
