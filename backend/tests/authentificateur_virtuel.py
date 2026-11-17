"""Authentificateur WebAuthn VIRTUEL pour les tests : joue le rôle du téléphone (clé ES256, empreinte « vérifiée »).
Fabrique de vraies réponses d'enregistrement (attestation « none ») et de connexion (signature) que le serveur doit valider comme celles d'un vrai téléphone."""
from __future__ import annotations

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from webauthn.helpers import base64url_to_bytes, bytes_to_base64url


class Telephone:
    def __init__(self, rp_id: str, origine: str):
        self.rp_id, self.origine = rp_id, origine
        self.cle = ec.generate_private_key(ec.SECP256R1())
        self.identifiant = os.urandom(32)
        self.compteur = 0

    def _cose(self) -> bytes:
        n = self.cle.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})

    def _client_data(self, type_: str, defi: str, origine: str | None = None) -> bytes:
        return json.dumps({"type": type_, "challenge": defi, "origin": origine or self.origine, "crossOrigin": False}).encode()

    def enregistrer(self, options: dict, origine: str | None = None, verification_utilisateur: bool = True) -> dict:
        defi = options["challenge"]
        drapeaux = 0x41 | (0x04 if verification_utilisateur else 0)                  # présence + (vérification) + données d'attestation
        auth = hashlib.sha256(self.rp_id.encode()).digest() + bytes([drapeaux]) + struct.pack(">I", 0) + b"\x00" * 16 + struct.pack(">H", len(self.identifiant)) + self.identifiant + self._cose()
        cd = self._client_data("webauthn.create", defi, origine)
        return {"id": bytes_to_base64url(self.identifiant), "rawId": bytes_to_base64url(self.identifiant), "type": "public-key",
                "response": {"clientDataJSON": bytes_to_base64url(cd), "attestationObject": bytes_to_base64url(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})),
                             "transports": ["internal"]}, "clientExtensionResults": {}}

    def signer(self, options: dict, origine: str | None = None, compteur: int | None = None, verification_utilisateur: bool = True) -> dict:
        self.compteur = self.compteur + 1 if compteur is None else compteur
        drapeaux = 0x01 | (0x04 if verification_utilisateur else 0)
        auth = hashlib.sha256(self.rp_id.encode()).digest() + bytes([drapeaux]) + struct.pack(">I", self.compteur)
        cd = self._client_data("webauthn.get", options["challenge"], origine)
        signature = self.cle.sign(auth + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": bytes_to_base64url(self.identifiant), "rawId": bytes_to_base64url(self.identifiant), "type": "public-key",
                "response": {"clientDataJSON": bytes_to_base64url(cd), "authenticatorData": bytes_to_base64url(auth), "signature": bytes_to_base64url(signature),
                             "userHandle": None}, "clientExtensionResults": {}}
