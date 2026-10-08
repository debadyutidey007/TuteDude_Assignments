#!/usr/bin/env python3
"""Cryptography and Blockchain Fundamentals: a menu-driven console application.

Menu actions
------------
1. SHA-256 hashing of a user-supplied message.
2. Digital signature: generate a public-private key pair, sign a message with the
   private key, then verify the signature with the public key.
3. Vehicle Registration System: register a vehicle (number plate, owner, model) and
   retrieve its details by number plate. Duplicate number plates are rejected.

Requirements: Python 3.10+ and ``pip install cryptography``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


# --------------------------------------------------------------------------- #
# SHA-256 hashing
# --------------------------------------------------------------------------- #
def sha256_hex(message: str) -> str:
    """Return the SHA-256 digest of ``message`` (UTF-8 encoded) as 64 hex digits."""
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Digital signature (RSASSA-PSS with SHA-256)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class KeyPair:
    """A public-private key pair."""

    private_key: rsa.RSAPrivateKey
    public_key: rsa.RSAPublicKey


class SignatureScheme:
    """RSASSA-PSS (RFC 8017) instantiated with SHA-256 and MGF1-SHA-256."""

    KEY_SIZE_BITS: Final[int] = 2048
    PUBLIC_EXPONENT: Final[int] = 65537

    _HASH: Final[hashes.HashAlgorithm] = hashes.SHA256()
    _PADDING: Final[padding.PSS] = padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=hashes.SHA256.digest_size,
    )

    @classmethod
    def generate_key_pair(cls) -> KeyPair:
        """Generate a fresh RSA public-private key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=cls.PUBLIC_EXPONENT,
            key_size=cls.KEY_SIZE_BITS,
        )
        return KeyPair(private_key=private_key, public_key=private_key.public_key())

    @classmethod
    def sign(cls, private_key: rsa.RSAPrivateKey, message: bytes) -> bytes:
        """Sign ``message`` with the private key."""
        return private_key.sign(message, cls._PADDING, cls._HASH)

    @classmethod
    def verify(
        cls, public_key: rsa.RSAPublicKey, message: bytes, signature: bytes
    ) -> bool:
        """Return True iff ``signature`` is a valid signature on ``message``."""
        try:
            public_key.verify(signature, message, cls._PADDING, cls._HASH)
        except InvalidSignature:
            return False
        return True


# --------------------------------------------------------------------------- #
# Vehicle Registration System
# --------------------------------------------------------------------------- #
class VehicleRegistryError(Exception):
    """Base class for vehicle-registry errors."""


class DuplicateVehicleError(VehicleRegistryError):
    """Raised when a number plate is already registered."""

    def __init__(self, number_plate: str) -> None:
        super().__init__(f"Number plate '{number_plate}' is already registered.")


class VehicleNotFoundError(VehicleRegistryError):
    """Raised when no vehicle is registered under a number plate."""

    def __init__(self, number_plate: str) -> None:
        super().__init__(f"No vehicle found with number plate '{number_plate}'.")


@dataclass(frozen=True, slots=True)
class Vehicle:
    """An immutable vehicle record."""

    number_plate: str
    owner: str
    model: str


class VehicleRegistry:
    """In-memory registry mapping a canonical number plate to its Vehicle."""

    def __init__(self) -> None:
        self._vehicles: dict[str, Vehicle] = {}

    @staticmethod
    def canonical(number_plate: str) -> str:
        """Case- and whitespace-insensitive form of a plate, used as the dict key."""
        return "".join(number_plate.split()).upper()

    def ensure_available(self, number_plate: str) -> str:
        """Return the canonical plate, or raise if it is already registered."""
        key = self.canonical(number_plate)
        if key in self._vehicles:
            raise DuplicateVehicleError(key)
        return key

    def register(self, number_plate: str, owner: str, model: str) -> Vehicle:
        """Store a new vehicle; raise DuplicateVehicleError on a repeated plate."""
        key = self.ensure_available(number_plate)
        vehicle = Vehicle(number_plate=key, owner=owner, model=model)
        self._vehicles[key] = vehicle
        return vehicle

    def get(self, number_plate: str) -> Vehicle:
        """Return the vehicle for a plate; raise VehicleNotFoundError if absent."""
        key = self.canonical(number_plate)
        try:
            return self._vehicles[key]
        except KeyError:
            raise VehicleNotFoundError(key) from None


# --------------------------------------------------------------------------- #
# Console interface
# --------------------------------------------------------------------------- #
class MenuOption(IntEnum):
    """Menu entries; the integer value is what the user types."""

    SHA256_HASH = 1
    DIGITAL_SIGNATURE = 2
    REGISTER_VEHICLE = 3
    GET_VEHICLE = 4
    EXIT = 5


MENU_LABELS: Final[dict[MenuOption, str]] = {
    MenuOption.SHA256_HASH: "Generate SHA-256 hash of a message",
    MenuOption.DIGITAL_SIGNATURE: "Create and verify a digital signature",
    MenuOption.REGISTER_VEHICLE: "Register a vehicle",
    MenuOption.GET_VEHICLE: "Retrieve vehicle details",
    MenuOption.EXIT: "Exit",
}


def read_required(prompt: str) -> str:
    """Prompt until the user enters a non-blank value; return it stripped."""
    while True:
        value = input(f"{prompt}: ").strip()
        if value:
            return value
        print("  This field cannot be empty. Please try again.")


class Application:
    """Menu-driven controller wiring user input to the underlying services."""

    def __init__(self) -> None:
        self._registry = VehicleRegistry()
        self._handlers: dict[MenuOption, Callable[[], None]] = {
            MenuOption.SHA256_HASH: self._hash_message,
            MenuOption.DIGITAL_SIGNATURE: self._sign_and_verify,
            MenuOption.REGISTER_VEHICLE: self._register_vehicle,
            MenuOption.GET_VEHICLE: self._get_vehicle,
        }

    def run(self) -> None:
        """Show the menu and execute the chosen action until the user exits."""
        while True:
            self._show_menu()
            option = self._read_option()
            if option is None:
                print(f"Invalid choice. Enter a number from 1 to {len(MenuOption)}.")
            elif option is MenuOption.EXIT:
                print("Goodbye!")
                return
            else:
                self._handlers[option]()

    # -- menu plumbing ------------------------------------------------------ #
    @staticmethod
    def _show_menu() -> None:
        width = 48
        print()
        print("=" * width)
        print("Cryptography & Blockchain Fundamentals".center(width))
        print("=" * width)
        for option, label in MENU_LABELS.items():
            print(f"  {option.value}. {label}")
        print("-" * width)

    @staticmethod
    def _read_option() -> MenuOption | None:
        try:
            return MenuOption(int(input("Enter your choice: ").strip()))
        except ValueError:
            return None

    # -- actions ------------------------------------------------------------ #
    @staticmethod
    def _hash_message() -> None:
        message = input("Enter the message to hash: ")
        print(f"SHA-256: {sha256_hex(message)}")

    @staticmethod
    def _sign_and_verify() -> None:
        key_pair = SignatureScheme.generate_key_pair()
        print(f"Public-private key pair generated (RSA-{SignatureScheme.KEY_SIZE_BITS}).")

        message = input("Enter the message to sign: ").encode("utf-8")
        signature = SignatureScheme.sign(key_pair.private_key, message)
        print(f"Signature (hex): {signature.hex()}")

        is_valid = SignatureScheme.verify(key_pair.public_key, message, signature)
        print(f"Signature verification: {'VALID' if is_valid else 'INVALID'}")

    def _register_vehicle(self) -> None:
        try:
            number_plate = self._registry.ensure_available(
                read_required("Enter Number Plate")
            )
            owner = read_required("Enter Owner Name")
            model = read_required("Enter Vehicle Model")
            vehicle = self._registry.register(number_plate, owner, model)
        except DuplicateVehicleError as error:
            print(f"Error: {error}")
            return
        print(f"Vehicle {vehicle.number_plate} registered successfully.")

    def _get_vehicle(self) -> None:
        try:
            vehicle = self._registry.get(read_required("Enter Number Plate"))
        except VehicleNotFoundError as error:
            print(f"Error: {error}")
            return
        print(f"Number Plate: {vehicle.number_plate}")
        print(f"Owner:        {vehicle.owner}")
        print(f"Model:        {vehicle.model}")


def main() -> None:
    """Program entry point."""
    try:
        Application().run()
    except (KeyboardInterrupt, EOFError):
        print("\nInput terminated. Goodbye!")


if __name__ == "__main__":
    main()