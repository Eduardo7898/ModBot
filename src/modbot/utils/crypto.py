"""Módulo de armazenamento e criptografia de credenciais do ModBot.

Utiliza exclusivamente a biblioteca padrão do Python (hashlib, hmac, secrets),
garantindo compatibilidade universal (Linux, Windows, macOS e Termux/Android)
sem dependências de compilação em C/Rust.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import platform
import secrets
import uuid
from pathlib import Path

CONFIG_DIR = Path.home() / ".modbot"
CONFIG_FILE = CONFIG_DIR / "config.enc"
SEED_FILE = CONFIG_DIR / ".device_seed"


def _legacy_device_seed() -> bytes:
    """Gera a semente antiga combinando dados voláteis do usuário e dispositivo."""
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "modbot_user"

    node = platform.node() or "localhost"
    try:
        hw_node = str(uuid.getnode())
    except Exception:
        hw_node = "123456789"

    seed_str = f"modbot:{user}:{node}:{hw_node}"
    return seed_str.encode("utf-8")


def _save_seed(seed: bytes) -> None:
    """Salva a semente no arquivo de configuração com permissões restritas."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _secure_dir_permissions(CONFIG_DIR)
        SEED_FILE.write_bytes(seed)
        _secure_file_permissions(SEED_FILE)
    except OSError:
        pass


def _get_device_seed() -> bytes:
    """Obtém ou gera uma semente persistente única para esta instalação/dispositivo.

    Garante compatibilidade e estabilidade entre execuções mesmo no Android/Termux
    (onde uuid.getnode() gera números aleatórios por restrições do SELinux e
    platform.node() muda com conexões de rede).
    """
    if SEED_FILE.is_file():
        try:
            seed = SEED_FILE.read_bytes().strip()
            if seed:
                return seed
        except OSError:
            pass

    # Se já existir um token antigo sem arquivo de semente, tenta migrar se for válido
    if CONFIG_FILE.is_file():
        legacy_seed = _legacy_device_seed()
        try:
            content = CONFIG_FILE.read_text(encoding="utf-8").strip()
            if content:
                decrypt_data(content, seed=legacy_seed)
                _save_seed(legacy_seed)
                return legacy_seed
        except Exception:
            pass

    # Gera semente permanente e criptograficamente segura
    new_seed = secrets.token_hex(32).encode("utf-8")
    _save_seed(new_seed)
    return new_seed


def _derive_keys(salt: bytes, seed: bytes | None = None) -> tuple[bytes, bytes]:
    """Deriva chave de cifragem (32 bytes) e chave de autenticação HMAC (32 bytes)."""
    derived = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=seed if seed is not None else _get_device_seed(),
        salt=salt,
        iterations=100_000,
        dklen=64,
    )
    return derived[:32], derived[32:]


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    """Gera um fluxo de bytes pseudo-aleatório em modo CTR utilizando HMAC-SHA256."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hmac.new(
            enc_key,
            nonce + counter.to_bytes(8, byteorder="big"),
            hashlib.sha256,
        ).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def encrypt_data(plaintext: str, seed: bytes | None = None) -> str:
    """Cifra um texto puro e retorna string codificada em base64 com HMAC."""
    raw_data = plaintext.encode("utf-8")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)

    enc_key, mac_key = _derive_keys(salt, seed=seed)
    stream = _keystream(enc_key, nonce, len(raw_data))
    ciphertext = bytes(a ^ b for a, b in zip(raw_data, stream))

    tag = hmac.new(mac_key, salt + nonce + ciphertext, hashlib.sha256).digest()

    payload = salt + nonce + tag + ciphertext
    return base64.b64encode(payload).decode("ascii")


def decrypt_data(encoded: str, seed: bytes | None = None) -> str:
    """Decifra um texto previamente encriptado com verificação de integridade."""
    try:
        payload = base64.b64decode(encoded.encode("ascii"))
    except Exception as exc:
        raise ValueError("Formato de payload inválido.") from exc

    if len(payload) < 64:  # 16 (salt) + 16 (nonce) + 32 (tag)
        raise ValueError("Dados encriptados incompletos ou corrompidos.")

    salt = payload[:16]
    nonce = payload[16:32]
    expected_tag = payload[32:64]
    ciphertext = payload[64:]

    enc_key, mac_key = _derive_keys(salt, seed=seed)
    calculated_tag = hmac.new(
        mac_key, salt + nonce + ciphertext, hashlib.sha256
    ).digest()

    if not hmac.compare_digest(expected_tag, calculated_tag):
        raise ValueError("Falha na integridade: chave incorreta ou dados corrompidos.")

    stream = _keystream(enc_key, nonce, len(ciphertext))
    plaintext_bytes = bytes(a ^ b for a, b in zip(ciphertext, stream))
    return plaintext_bytes.decode("utf-8")


def _secure_file_permissions(path: Path) -> None:
    """Aplica permissões restritas (0600) se estiver em sistema POSIX."""
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _secure_dir_permissions(path: Path) -> None:
    """Aplica permissões restritas (0700) ao diretório se estiver em sistema POSIX."""
    if os.name == "posix":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def save_token(token: str) -> None:
    """Salva o token do Discord criptografado no arquivo ~/.modbot/config.enc."""
    token = token.strip()
    if not token:
        raise ValueError("O token não pode estar vazio.")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _secure_dir_permissions(CONFIG_DIR)

    encrypted = encrypt_data(token)
    CONFIG_FILE.write_text(encrypted, encoding="utf-8")
    _secure_file_permissions(CONFIG_FILE)


def load_token() -> str | None:
    """Carrega e decifra o token salvo.

    Retorna None se não existir ou estiver inválido.
    """
    if not CONFIG_FILE.is_file():
        return None

    try:
        content = CONFIG_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return decrypt_data(content)
    except Exception:
        return None


def has_token() -> bool:
    """Verifica se há um token configurado e válido."""
    return load_token() is not None


def remove_token() -> bool:
    """Remove o token configurado e sua semente. Retorna True se excluído."""
    removed = False
    if CONFIG_FILE.exists():
        try:
            CONFIG_FILE.unlink()
            removed = True
        except OSError:
            pass
    if SEED_FILE.exists():
        try:
            SEED_FILE.unlink()
        except OSError:
            pass
    return removed
