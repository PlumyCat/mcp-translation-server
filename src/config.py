"""
Configuration du serveur MCP de traduction
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration centralisée du serveur MCP"""

    # Serveur MCP
    MCP_SERVER_PORT = int(os.getenv('MCP_SERVER_PORT', 3000))
    MCP_LOG_LEVEL = os.getenv('MCP_LOG_LEVEL', 'INFO')

    # Azure Storage
    AZURE_ACCOUNT_NAME = os.getenv('AZURE_ACCOUNT_NAME')
    AZURE_ACCOUNT_KEY = os.getenv('AZURE_ACCOUNT_KEY')
    INPUT_CONTAINER = os.getenv('INPUT_CONTAINER', 'doc-to-trad')
    OUTPUT_CONTAINER = os.getenv('OUTPUT_CONTAINER', 'doc-trad')

    # Azure Translator
    TRANSLATOR_KEY = os.getenv('TRANSLATOR_TEXT_SUBSCRIPTION_KEY')
    TRANSLATOR_ENDPOINT = os.getenv('TRANSLATOR_TEXT_ENDPOINT')
    TRANSLATOR_REGION = os.getenv('TRANSLATOR_REGION')

    # Microsoft Graph (OneDrive)
    CLIENT_ID = os.getenv('CLIENT_ID')
    CLIENT_SECRET = os.getenv('SECRET_ID')
    TENANT_ID = os.getenv('TENANT_ID')
    ONEDRIVE_FOLDER = os.getenv('ONEDRIVE_FOLDER')

    # Limites
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 100))
    MAX_TRANSLATION_TIME_MINUTES = int(
        os.getenv('MAX_TRANSLATION_TIME_MINUTES', 30))
    CLEANUP_INTERVAL_HOURS = int(os.getenv('CLEANUP_INTERVAL_HOURS', 1))

    @classmethod
    def validate(cls) -> list:
        """Valide la configuration et retourne les erreurs"""
        errors = []

        # Validation Azure Storage
        if not cls.AZURE_ACCOUNT_NAME:
            errors.append("AZURE_ACCOUNT_NAME manquant")
        if not cls.AZURE_ACCOUNT_KEY:
            errors.append("AZURE_ACCOUNT_KEY manquant")

        # Validation Azure Translator
        if not cls.TRANSLATOR_KEY:
            errors.append("TRANSLATOR_TEXT_SUBSCRIPTION_KEY manquant")
        if not cls.TRANSLATOR_ENDPOINT:
            errors.append("TRANSLATOR_TEXT_ENDPOINT manquant")

        # MS Graph optionnel (warning seulement)
        if not all([cls.CLIENT_ID, cls.CLIENT_SECRET, cls.TENANT_ID]):
            errors.append(
                "Configuration MS Graph incomplète (OneDrive non disponible)")

        return errors

    @classmethod
    def get_storage_url(cls) -> str:
        """URL du service Azure Storage"""
        return f"https://{cls.AZURE_ACCOUNT_NAME}.blob.core.windows.net"

    @classmethod
    def get_translator_batch_url(cls) -> str:
        """URL de l'API Batch Translation"""
        endpoint = cls.TRANSLATOR_ENDPOINT
        if not endpoint.endswith("/"):
            endpoint += "/"
        return f"{endpoint}translator/text/batch/v1.1/batches"
