/-
TheoriaKit — a deliberately tiny Lean 4 lemma kit for the Theoria assistant.

No Mathlib: every proof uses only core Lean 4 tactics (rfl, simp, decide,
omega, induction, exact), so the whole toolchain fits in ~1.5 GB of disk and
verification never needs the network. These lemmas double as the curriculum
of statements the fine-tuned model learns to emit in ```lean blocks.
-/

namespace TheoriaKit

/-! ### Natural number arithmetic -/

theorem add_zero' (n : Nat) : n + 0 = n := rfl

theorem zero_add' (n : Nat) : 0 + n = n := by simp

theorem add_comm' (a b : Nat) : a + b = b + a := Nat.add_comm a b

theorem add_assoc' (a b c : Nat) : (a + b) + c = a + (b + c) := Nat.add_assoc a b c

theorem mul_comm' (a b : Nat) : a * b = b * a := Nat.mul_comm a b

theorem mul_assoc' (a b c : Nat) : (a * b) * c = a * (b * c) := Nat.mul_assoc a b c

theorem mul_one' (n : Nat) : n * 1 = n := Nat.mul_one n

theorem left_distrib' (a b c : Nat) : a * (b + c) = a * b + a * c :=
  Nat.left_distrib a b c

/-! ### Order -/

theorem succ_pos' (n : Nat) : 0 < n + 1 := by omega

theorem le_add_right' (a b : Nat) : a ≤ a + b := by omega

theorem lt_trans' (a b c : Nat) (h1 : a < b) (h2 : b < c) : a < c := by omega

theorem no_nat_between (n : Nat) (h : 0 < n) : ¬ n < 1 := by omega

theorem square_nonneg (a : Nat) : 0 ≤ a * a := Nat.zero_le _

/-! ### Parity -/

theorem two_mul_is_even (n : Nat) : (2 * n) % 2 = 0 := by omega

theorem even_add_even (a b : Nat) (ha : a % 2 = 0) (hb : b % 2 = 0) :
    (a + b) % 2 = 0 := by omega

theorem odd_add_odd (a b : Nat) (ha : a % 2 = 1) (hb : b % 2 = 1) :
    (a + b) % 2 = 0 := by omega

theorem even_mul_any (a b : Nat) (ha : a % 2 = 0) : (a * b) % 2 = 0 := by
  simp [Nat.mul_mod, ha]

theorem even_square (k : Nat) : ((2 * k) * (2 * k)) % 2 = 0 := by
  simp [Nat.mul_mod]

/-! ### Bounded checks by decision procedure -/

theorem fermat_little_5 : ∀ n : Fin 5, (n.val ^ 5) % 5 = n.val % 5 := by decide

/-- Core Lean has no `Nat.Prime` (that's Mathlib), so define a decidable check. -/
def isPrime (n : Nat) : Bool :=
  2 ≤ n && (List.range n).all fun d => d < 2 || n % d != 0

theorem two_is_prime : isPrime 2 = true := by decide

theorem no_even_prime_gt_two :
    ∀ n : Fin 20, n.val > 2 → n.val % 2 = 0 → isPrime n.val = false := by decide

/-! ### Induction examples -/

def sumTo : Nat → Nat
  | 0 => 0
  | n + 1 => sumTo n + (n + 1)

theorem two_mul_sumTo (n : Nat) : 2 * sumTo n = n * (n + 1) := by
  induction n with
  | zero => rfl
  | succ k ih =>
    show 2 * (sumTo k + (k + 1)) = (k + 1) * (k + 2)
    rw [Nat.left_distrib, ih]
    -- k * (k + 1) + 2 * (k + 1) = (k + 1) * (k + 2): linear in the product
    -- terms once k * (k + 1) is treated atomically, but omega needs full
    -- linearity, so finish by ring-free rewriting.
    rw [Nat.mul_comm k (k + 1), Nat.mul_comm 2 (k + 1), ← Nat.left_distrib]

theorem pow_two_eq_mul_self (n : Nat) : n ^ 2 = n * n := by
  rw [Nat.pow_succ, Nat.pow_one]

/-! ### Extra curriculum for fill-the-sorry demos -/

theorem add_right_cancel (a b c : Nat) (h : a + c = b + c) : a = b := by omega

theorem mul_zero' (n : Nat) : n * 0 = 0 := by simp

theorem zero_mul' (n : Nat) : 0 * n = 0 := by simp

theorem lt_succ_self (n : Nat) : n < n + 1 := by omega

theorem not_lt_self (n : Nat) : ¬ n < n := by omega

theorem mod_two_lt (n : Nat) : n % 2 < 2 := by omega

theorem add_assoc_four (a b c d : Nat) : ((a + b) + c) + d = a + (b + (c + d)) := by omega

end TheoriaKit
