"""
Voting Management System on a Simple Blockchain
================================================

A menu-driven console application. Every accepted vote is sealed into its own
block, and each block is linked to its predecessor through a SHA-256 hash, so
any later modification of the ledger is detected by "Validate Chain".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Final, NamedTuple

GENESIS_PREVIOUS_HASH: Final[str] = "0" * 64

def utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
class VotingError(Exception):
    """Raised when an operation violates a rule of the voting system."""

@dataclass
class Voter:
    voter_id: str
    name: str
    has_voted: bool = False


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    name: str


@dataclass(frozen=True)
class Transaction:
    """A single vote: voter -> candidate."""

    voter_id: str
    candidate_id: str

    def __str__(self) -> str:
        return f"Voter {self.voter_id} -> Candidate {self.candidate_id}"


# --------------------------------------------------------------------------- #
# Blockchain
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    index: int
    timestamp: str
    transactions: tuple[Transaction, ...]
    previous_hash: str
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """SHA-256 over the canonical JSON encoding of the block's contents."""
        payload = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "transactions": [asdict(tx) for tx in self.transactions],
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ValidationResult(NamedTuple):
    is_valid: bool
    message: str


class Blockchain:
    """Append-only sequence of blocks linked by their hashes."""

    def __init__(self) -> None:
        genesis = Block(0, utc_timestamp(), (), GENESIS_PREVIOUS_HASH)
        self.chain: list[Block] = [genesis]

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def add_block(self, transactions: Iterable[Transaction]) -> Block:
        block = Block(
            index=len(self.chain),
            timestamp=utc_timestamp(),
            transactions=tuple(transactions),
            previous_hash=self.last_block.hash,
        )
        self.chain.append(block)
        return block

    def validate(self) -> ValidationResult:
        """Re-derive every hash and link; report the first inconsistency."""
        expected_previous_hash = GENESIS_PREVIOUS_HASH
        for position, block in enumerate(self.chain):
            if block.index != position:
                return ValidationResult(
                    False,
                    f"Block #{position} carries the wrong index ({block.index}).",
                )
            if block.previous_hash != expected_previous_hash:
                return ValidationResult(
                    False,
                    f"Block #{position} is not linked to the hash of the block "
                    "before it.",
                )
            if block.hash != block.compute_hash():
                return ValidationResult(
                    False,
                    f"Block #{position} has been altered: its stored hash does "
                    "not match its contents.",
                )
            expected_previous_hash = block.hash
        return ValidationResult(True, f"{len(self.chain)} block(s) verified.")


# --------------------------------------------------------------------------- #
# Voting rules
# --------------------------------------------------------------------------- #
class VotingSystem:
    """Registry of voters and candidates plus the rules for casting a vote."""

    def __init__(self) -> None:
        self._candidates: dict[str, Candidate] = {}
        self._voters: dict[str, Voter] = {}
        self.blockchain = Blockchain()

    @staticmethod
    def _required(value: str, label: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise VotingError(f"{label} cannot be empty.")
        return cleaned

    def add_candidate(self, candidate_id: str, name: str) -> Candidate:
        candidate_id = self._required(candidate_id, "Candidate ID")
        name = self._required(name, "Candidate name")
        if candidate_id in self._candidates:
            raise VotingError(f"Candidate ID '{candidate_id}' already exists.")
        candidate = Candidate(candidate_id, name)
        self._candidates[candidate_id] = candidate
        return candidate

    def add_voter(self, voter_id: str, name: str) -> Voter:
        voter_id = self._required(voter_id, "Voter ID")
        name = self._required(name, "Voter name")
        if voter_id in self._voters:
            raise VotingError(f"Voter ID '{voter_id}' already exists.")
        voter = Voter(voter_id, name)
        self._voters[voter_id] = voter
        return voter

    def cast_vote(self, voter_id: str, candidate_id: str) -> Block:
        voter_id = self._required(voter_id, "Voter ID")
        candidate_id = self._required(candidate_id, "Candidate ID")

        voter = self._voters.get(voter_id)
        if voter is None:
            raise VotingError(f"Voter ID '{voter_id}' is not registered.")
        if voter.has_voted:
            raise VotingError(f"Voter '{voter_id}' has already voted.")
        if candidate_id not in self._candidates:
            raise VotingError(f"Candidate ID '{candidate_id}' is not registered.")

        block = self.blockchain.add_block([Transaction(voter_id, candidate_id)])
        voter.has_voted = True  # only after the vote is safely on the chain
        return block


# --------------------------------------------------------------------------- #
# Console interface
# --------------------------------------------------------------------------- #
class MenuOption(Enum):
    ADD_CANDIDATE = ("1", "Add Candidate")
    ADD_VOTER = ("2", "Add Voter")
    CAST_VOTE = ("3", "Cast Vote")
    PRINT_BLOCKCHAIN = ("4", "Print Blockchain")
    VALIDATE_CHAIN = ("5", "Validate Chain")
    EXIT = ("6", "Exit")

    def __init__(self, key: str, label: str) -> None:
        self.key = key
        self.label = label

    @classmethod
    def from_key(cls, key: str) -> MenuOption | None:
        return next((option for option in cls if option.key == key), None)


class VotingApp:
    """Menu-driven console front end for the voting system."""

    def __init__(self) -> None:
        self.system = VotingSystem()
        self._handlers: dict[MenuOption, Callable[[], None]] = {
            MenuOption.ADD_CANDIDATE: self._add_candidate,
            MenuOption.ADD_VOTER: self._add_voter,
            MenuOption.CAST_VOTE: self._cast_vote,
            MenuOption.PRINT_BLOCKCHAIN: self._print_blockchain,
            MenuOption.VALIDATE_CHAIN: self._validate_chain,
        }

    def run(self) -> None:
        while True:
            self._print_menu()
            option = MenuOption.from_key(input("Enter your choice (1-6): ").strip())
            if option is None:
                print("Invalid choice. Please enter a number from 1 to 6.")
            elif option is MenuOption.EXIT:
                print("Exiting the Voting Management System.")
                return
            else:
                try:
                    self._handlers[option]()
                except VotingError as error:
                    print(f"Error: {error}")

    @staticmethod
    def _print_menu() -> None:
        print("\n===== Voting Management System =====")
        for option in MenuOption:
            print(f"{option.key}. {option.label}")

    # ---- actions ---------------------------------------------------------- #
    def _add_candidate(self) -> None:
        candidate_id = input("Candidate ID: ")
        name = input("Candidate name: ")
        candidate = self.system.add_candidate(candidate_id, name)
        print(f"Candidate added: {candidate.candidate_id} - {candidate.name}")

    def _add_voter(self) -> None:
        voter_id = input("Voter ID: ")
        name = input("Voter name: ")
        voter = self.system.add_voter(voter_id, name)
        print(f"Voter added: {voter.voter_id} - {voter.name}")

    def _cast_vote(self) -> None:
        voter_id = input("Voter ID: ")
        candidate_id = input("Candidate ID to vote for: ")
        block = self.system.cast_vote(voter_id, candidate_id)
        print(f"Vote recorded in block #{block.index}.")

    def _print_blockchain(self) -> None:
        for block in self.system.blockchain.chain:
            genesis_tag = " (Genesis)" if block.index == 0 else ""
            print(f"\nBlock #{block.index}{genesis_tag}")
            print(f"  Timestamp     : {block.timestamp}")
            print(f"  Transactions  : {len(block.transactions)}")
            for transaction in block.transactions:
                print(f"      {transaction}")
            print(f"  Previous Hash : {block.previous_hash}")
            print(f"  Hash          : {block.hash}")

    def _validate_chain(self) -> None:
        result = self.system.blockchain.validate()
        status = "VALID" if result.is_valid else "INVALID"
        print(f"Chain status: {status}. {result.message}")


def main() -> None:
    try:
        VotingApp().run()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting the Voting Management System.")


if __name__ == "__main__":
    main()