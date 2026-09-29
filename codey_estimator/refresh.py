import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Final, TypeAlias

from codey_estimator.errors import BudgetExceededError, PricingPolicyError

EpochSeconds: TypeAlias = int
Clock: TypeAlias = Callable[[], float]
SECONDS_PER_DAY: Final[int] = 86_400


class RefreshStatus(StrEnum):
    OK = "ok"
    PENDING = "pending"
    FAILED = "failed"
    DISABLED = "disabled"


class RefreshClass(StrEnum):
    NORMAL = "normal"
    FREQUENT = "frequent"
    VOLATILE = "volatile"
    HIGH_VALUE = "high_value"
    OVERRIDE = "override"


_CLASS_PRECEDENCE: Final[dict[RefreshClass, int]] = {
    RefreshClass.VOLATILE: 0,
    RefreshClass.HIGH_VALUE: 1,
    RefreshClass.FREQUENT: 2,
    RefreshClass.NORMAL: 3,
}


def _read_clock(now_fn: Clock) -> Fraction:
    value = now_fn()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"now_fn() must return int or float, got {type(value)!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise PricingPolicyError("CLOCK_NOT_FINITE", "now_fn() returned a non-finite float")
    return Fraction(value)


def _check_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value)!r}")


@dataclass(frozen=True, slots=True)
class RefreshPolicyConfig:
    normal_interval_days: int = 180
    frequent_interval_days: int = 90
    frequent_min_uses: int = 5
    frequent_window_days: int = 90
    volatile_categories: tuple[tuple[str, int], ...] = (
        ("copper", 30),
        ("lumber", 30),
        ("sheet_goods", 30),
    )
    high_value_threshold_cents: int = 10_000
    high_value_interval_days: int = 60

    def __post_init__(self) -> None:
        _check_int(self.normal_interval_days, "normal_interval_days")
        _check_int(self.frequent_interval_days, "frequent_interval_days")
        _check_int(self.frequent_min_uses, "frequent_min_uses")
        _check_int(self.frequent_window_days, "frequent_window_days")
        _check_int(self.high_value_threshold_cents, "high_value_threshold_cents")
        _check_int(self.high_value_interval_days, "high_value_interval_days")
        for key, interval in self.volatile_categories:
            if not isinstance(key, str):
                raise TypeError(f"volatile category key must be a str, got {type(key)!r}")
            _check_int(interval, "volatile category interval")

        if (
            self.normal_interval_days < 1
            or self.frequent_interval_days < 1
            or self.high_value_interval_days < 1
            or any(interval < 1 for _, interval in self.volatile_categories)
        ):
            raise PricingPolicyError("INTERVAL_INVALID", "every interval must be >= 1 day")
        if self.frequent_min_uses < 1 or self.frequent_window_days < 1:
            raise PricingPolicyError(
                "FREQUENT_RULE_INVALID", "frequent_min_uses and frequent_window_days must be >= 1"
            )
        if self.high_value_threshold_cents < 1:
            raise PricingPolicyError(
                "HIGH_VALUE_THRESHOLD_INVALID", "high_value_threshold_cents must be >= 1"
            )

        seen: set[str] = set()
        for key, _interval in self.volatile_categories:
            if not key or key != key.strip().lower():
                raise PricingPolicyError(
                    "CATEGORY_KEY_INVALID", f"category key {key!r} is not normalized"
                )
            if key in seen:
                raise PricingPolicyError(
                    "CATEGORY_KEY_DUPLICATE", f"duplicate category key {key!r}"
                )
            seen.add(key)


@dataclass(frozen=True, slots=True)
class RefreshSubject:
    category_key: str | None
    package_price_cents: int | None
    uses_in_window: int
    last_checked_at: EpochSeconds | None
    next_refresh_at: EpochSeconds | None
    refresh_status: RefreshStatus = RefreshStatus.OK
    override_interval_days: int | None = None


@dataclass(frozen=True, slots=True)
class IntervalChoice:
    refresh_class: RefreshClass
    interval_days: int


def _validate_subject(subject: RefreshSubject) -> None:
    _check_int(subject.uses_in_window, "uses_in_window")
    if subject.uses_in_window < 0:
        raise PricingPolicyError("SUBJECT_INVALID", "uses_in_window must be >= 0")
    if subject.package_price_cents is not None:
        _check_int(subject.package_price_cents, "package_price_cents")
        if subject.package_price_cents < 0:
            raise PricingPolicyError("SUBJECT_INVALID", "package_price_cents must be >= 0")
    if subject.override_interval_days is not None:
        _check_int(subject.override_interval_days, "override_interval_days")
        if subject.override_interval_days < 1:
            raise PricingPolicyError("SUBJECT_INVALID", "override_interval_days must be >= 1")
    if subject.last_checked_at is not None:
        _check_int(subject.last_checked_at, "last_checked_at")
    if subject.next_refresh_at is not None:
        _check_int(subject.next_refresh_at, "next_refresh_at")


class RefreshPolicy:
    def __init__(self, config: RefreshPolicyConfig | None = None) -> None:
        self._config = config if config is not None else RefreshPolicyConfig()

    @property
    def config(self) -> RefreshPolicyConfig:
        return self._config

    def classify(self, subject: RefreshSubject) -> IntervalChoice:
        _validate_subject(subject)
        cfg = self._config

        if subject.override_interval_days is not None:
            return IntervalChoice(RefreshClass.OVERRIDE, subject.override_interval_days)

        candidates: list[IntervalChoice] = [
            IntervalChoice(RefreshClass.NORMAL, cfg.normal_interval_days)
        ]
        if subject.uses_in_window >= cfg.frequent_min_uses:
            candidates.append(IntervalChoice(RefreshClass.FREQUENT, cfg.frequent_interval_days))
        if subject.category_key is not None:
            normalized = subject.category_key.strip().lower()
            for key, interval in cfg.volatile_categories:
                if key == normalized:
                    candidates.append(IntervalChoice(RefreshClass.VOLATILE, interval))
                    break
        if (
            subject.package_price_cents is not None
            and subject.package_price_cents >= cfg.high_value_threshold_cents
        ):
            candidates.append(
                IntervalChoice(RefreshClass.HIGH_VALUE, cfg.high_value_interval_days)
            )

        return min(
            candidates,
            key=lambda choice: (choice.interval_days, _CLASS_PRECEDENCE[choice.refresh_class]),
        )

    def is_due(self, subject: RefreshSubject, now: EpochSeconds) -> bool:
        _validate_subject(subject)
        _check_int(now, "now")

        if subject.refresh_status in (
            RefreshStatus.DISABLED,
            RefreshStatus.FAILED,
            RefreshStatus.PENDING,
        ):
            return False
        if subject.last_checked_at is None:
            return True
        if subject.next_refresh_at is not None:
            return now >= subject.next_refresh_at
        interval_days = self.classify(subject).interval_days
        return now >= subject.last_checked_at + interval_days * SECONDS_PER_DAY

    def next_refresh_at(self, subject: RefreshSubject, checked_at: EpochSeconds) -> EpochSeconds:
        _validate_subject(subject)
        _check_int(checked_at, "checked_at")
        interval_days = self.classify(subject).interval_days
        return checked_at + interval_days * SECONDS_PER_DAY


def is_search_cache_fresh(fetched_at: EpochSeconds, now: EpochSeconds, max_age_days: int) -> bool:
    _check_int(fetched_at, "fetched_at")
    _check_int(now, "now")
    _check_int(max_age_days, "max_age_days")
    if max_age_days < 1:
        raise PricingPolicyError("MAX_AGE_INVALID", "max_age_days must be >= 1")
    return now - fetched_at < max_age_days * SECONDS_PER_DAY


class TokenBucket:
    def __init__(
        self,
        capacity: int,
        refill_tokens: int,
        refill_period_seconds: int,
        now_fn: Clock,
    ) -> None:
        _check_int(capacity, "capacity")
        _check_int(refill_tokens, "refill_tokens")
        _check_int(refill_period_seconds, "refill_period_seconds")
        if capacity < 1 or refill_tokens < 1 or refill_period_seconds < 1:
            raise PricingPolicyError(
                "BUCKET_CONFIG_INVALID",
                "capacity, refill_tokens and refill_period_seconds must each be >= 1",
            )
        self._capacity = capacity
        self._rate = Fraction(refill_tokens, refill_period_seconds)
        self._now_fn = now_fn
        self._tokens = Fraction(capacity)
        self._last = _read_clock(now_fn)

    @classmethod
    def per_minute(cls, rate_per_min: int, now_fn: Clock) -> "TokenBucket":
        return cls(rate_per_min, rate_per_min, 60, now_fn)

    def _refill(self) -> None:
        now = _read_clock(self._now_fn)
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(Fraction(self._capacity), self._tokens + elapsed * self._rate)
            self._last = now

    def _validate_n(self, n: int) -> None:
        _check_int(n, "n")
        if n < 1:
            raise PricingPolicyError("TOKENS_INVALID", "n must be >= 1")
        if n > self._capacity:
            raise PricingPolicyError("TOKENS_EXCEED_CAPACITY", "n exceeds bucket capacity")

    def available(self) -> Fraction:
        self._refill()
        return self._tokens

    def try_acquire(self, n: int = 1) -> bool:
        self._validate_n(n)
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    def seconds_until_available(self, n: int = 1) -> Fraction:
        self._validate_n(n)
        self._refill()
        if self._tokens >= n:
            return Fraction(0)
        return (n - self._tokens) / self._rate


@dataclass(frozen=True, slots=True)
class BudgetState:
    day_index: int
    used: int


class DailyBudget:
    def __init__(
        self,
        daily_cap: int,
        now_fn: Clock,
        *,
        utc_offset_seconds: int = 0,
        state: BudgetState | None = None,
    ) -> None:
        _check_int(daily_cap, "daily_cap")
        if daily_cap < 0:
            raise PricingPolicyError("BUDGET_CONFIG_INVALID", "daily_cap must be >= 0")
        _check_int(utc_offset_seconds, "utc_offset_seconds")
        if abs(utc_offset_seconds) > 86_400:
            raise PricingPolicyError(
                "BUDGET_CONFIG_INVALID", "utc_offset_seconds must be within +/- 86400"
            )
        self._cap = daily_cap
        self._now_fn = now_fn
        self._offset = utc_offset_seconds
        if state is not None:
            _check_int(state.day_index, "state.day_index")
            _check_int(state.used, "state.used")
            if state.used < 0:
                raise PricingPolicyError("BUDGET_STATE_INVALID", "state.used must be >= 0")
            self._state = state
        else:
            self._state = BudgetState(self._current_day(), 0)

    def _current_day(self) -> int:
        now = _read_clock(self._now_fn)
        return math.floor((now + self._offset) / SECONDS_PER_DAY)

    def _effective_used(self) -> int:
        if self._current_day() > self._state.day_index:
            return 0
        return self._state.used

    def remaining(self) -> int:
        return max(0, self._cap - self._effective_used())

    def would_exceed(self, n: int = 1) -> bool:
        _check_int(n, "n")
        if n < 1:
            raise PricingPolicyError("AMOUNT_INVALID", "n must be >= 1")
        return self._effective_used() + n > self._cap

    def consume(self, n: int = 1) -> int:
        _check_int(n, "n")
        if n < 1:
            raise PricingPolicyError("AMOUNT_INVALID", "n must be >= 1")
        effective_used = self._effective_used()
        current_day = self._current_day()
        if effective_used + n > self._cap:
            raise BudgetExceededError(self._cap, effective_used, n)
        self._state = BudgetState(max(self._state.day_index, current_day), effective_used + n)
        return self.remaining()

    def snapshot(self) -> BudgetState:
        current_day = self._current_day()
        return BudgetState(max(self._state.day_index, current_day), self._effective_used())


def backoff_seconds(
    attempt: int,
    *,
    base_seconds: int = 60,
    factor: int = 2,
    max_seconds: int = 86_400,
) -> int:
    _check_int(attempt, "attempt")
    _check_int(base_seconds, "base_seconds")
    _check_int(factor, "factor")
    _check_int(max_seconds, "max_seconds")
    if attempt < 1:
        raise PricingPolicyError("BACKOFF_ATTEMPT_INVALID", "attempt must be >= 1")
    if base_seconds < 1 or factor < 1 or max_seconds < base_seconds:
        raise PricingPolicyError(
            "BACKOFF_CONFIG_INVALID",
            "base_seconds and factor must be >= 1, and max_seconds >= base_seconds",
        )

    value = base_seconds
    remaining_steps = attempt - 1
    while remaining_steps > 0 and value < max_seconds:
        value *= factor
        remaining_steps -= 1
    return min(value, max_seconds)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: int, now_fn: Clock) -> None:
        _check_int(failure_threshold, "failure_threshold")
        _check_int(cooldown_seconds, "cooldown_seconds")
        if failure_threshold < 1 or cooldown_seconds < 1:
            raise PricingPolicyError(
                "BREAKER_CONFIG_INVALID", "failure_threshold and cooldown_seconds must be >= 1"
            )
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._now_fn = now_fn
        self._stored_state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: Fraction | None = None
        self._probe_in_flight = False

    def _effective_state(self) -> CircuitState:
        if self._stored_state is CircuitState.OPEN:
            assert self._opened_at is not None
            now = _read_clock(self._now_fn)
            if now >= self._opened_at + self._cooldown:
                return CircuitState.HALF_OPEN
        return self._stored_state

    @property
    def state(self) -> CircuitState:
        return self._effective_state()

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def allow_request(self) -> bool:
        effective = self._effective_state()
        if effective is CircuitState.CLOSED:
            return True
        if effective is CircuitState.OPEN:
            return False
        self._stored_state = CircuitState.HALF_OPEN
        if not self._probe_in_flight:
            self._probe_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        effective = self._effective_state()
        if effective is CircuitState.CLOSED:
            self._consecutive_failures = 0
            return
        if effective is CircuitState.HALF_OPEN:
            self._stored_state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._probe_in_flight = False
            return

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        effective = self._effective_state()
        if effective is CircuitState.CLOSED:
            if self._consecutive_failures >= self._threshold:
                self._stored_state = CircuitState.OPEN
                self._opened_at = _read_clock(self._now_fn)
            return
        if effective is CircuitState.HALF_OPEN:
            self._stored_state = CircuitState.OPEN
            self._opened_at = _read_clock(self._now_fn)
            self._probe_in_flight = False
            return
