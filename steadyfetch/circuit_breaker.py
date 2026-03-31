"""Circuit breaker pattern for domain-level failure tracking."""

import time
from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    CLOSED = "closed"        # normal operation
    OPEN = "open"            # blocking requests — too many failures
    HALF_OPEN = "half_open"  # testing if service recovered


@dataclass
class DomainCircuit:
    failure_count: int = 0
    last_failure: float = 0.0
    state: State = State.CLOSED
    half_open_attempts: int = 0


class CircuitBreaker:
    """Per-domain circuit breaker.

    After `threshold` consecutive failures for a domain, the circuit opens
    and all requests are rejected for `cooldown` seconds. After cooldown,
    one test request is allowed (half-open). If it succeeds, the circuit
    resets. If it fails, the circuit re-opens.
    """

    def __init__(self, threshold: int = 5, cooldown: float = 120.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._circuits: dict[str, DomainCircuit] = {}

    def _get(self, domain: str) -> DomainCircuit:
        if domain not in self._circuits:
            self._circuits[domain] = DomainCircuit()
        return self._circuits[domain]

    def can_request(self, domain: str) -> bool:
        circuit = self._get(domain)

        if circuit.state == State.CLOSED:
            return True

        if circuit.state == State.OPEN:
            elapsed = time.time() - circuit.last_failure
            if elapsed >= self.cooldown:
                circuit.state = State.HALF_OPEN
                circuit.half_open_attempts = 0
                return True
            return False

        # half_open: allow one test request
        if circuit.half_open_attempts < 1:
            circuit.half_open_attempts += 1
            return True
        return False

    def record_success(self, domain: str) -> None:
        circuit = self._get(domain)
        circuit.failure_count = 0
        circuit.state = State.CLOSED

    def record_failure(self, domain: str) -> None:
        circuit = self._get(domain)
        circuit.failure_count += 1
        circuit.last_failure = time.time()

        if circuit.state == State.HALF_OPEN:
            circuit.state = State.OPEN
            return

        if circuit.failure_count >= self.threshold:
            circuit.state = State.OPEN

    def get_status(self, domain: str) -> dict:
        circuit = self._get(domain)
        return {
            "domain": domain,
            "state": circuit.state.value,
            "failure_count": circuit.failure_count,
            "cooldown_remaining": max(
                0, self.cooldown - (time.time() - circuit.last_failure)
            ) if circuit.state == State.OPEN else 0,
        }
