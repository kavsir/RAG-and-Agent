"""
Robustness Benchmark V3 Mutation Engine: Động cơ đột biến chuỗi tất định (Deterministic Fuzzing & Mutation).
Hỗ trợ tái tạo 100% kết quả dựa trên seed ngẫu nhiên cố định (Default: 20260906).
"""
import random
import unicodedata
import re
from typing import List, Tuple, Optional, Callable


VIETNAMESE_ACCENTS_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'đ': 'd',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
}

ENGLISH_VIETNAMESE_REPLACEMENTS = [
    (r"\btín chỉ\b", "credits"),
    (r"\bgiảng viên\b", "lecturer"),
    (r"\bai dạy\b", "who teaches"),
    (r"\bhọc kỳ\b", "semester"),
    (r"\bnhắc tôi\b", "remind me"),
    (r"\bđặt lịch\b", "set reminder"),
    (r"\bgửi email\b", "send email"),
    (r"\bkhóa luận\b", "thesis"),
    (r"\blộ trình\b", "roadmap"),
]


class MutationEngine:
    def __init__(self, seed: int = 20260906):
        self.seed = seed
        self.rng = random.Random(seed)

    def reseed(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed)

    def op_char_delete(self, text: str) -> str:
        if len(text) <= 3:
            return text
        idx = self.rng.randint(0, len(text) - 1)
        return text[:idx] + text[idx + 1:]

    def op_char_insert(self, text: str) -> str:
        idx = self.rng.randint(0, len(text))
        ch = self.rng.choice("abcdefghijklmnopqrstuvwxyz0123456789 ")
        return text[:idx] + ch + text[idx:]

    def op_char_substitute(self, text: str) -> str:
        if not text:
            return text
        idx = self.rng.randint(0, len(text) - 1)
        ch = self.rng.choice("abcdefghijklmnopqrstuvwxyz_")
        return text[:idx] + ch + text[idx + 1:]

    def op_char_transpose(self, text: str) -> str:
        if len(text) < 2:
            return text
        idx = self.rng.randint(0, len(text) - 2)
        return text[:idx] + text[idx + 1] + text[idx] + text[idx + 2:]

    def op_space_insert(self, text: str) -> str:
        if not text:
            return text
        idx = self.rng.randint(0, len(text))
        return text[:idx] + "  " + text[idx:]

    def op_space_remove(self, text: str) -> str:
        spaces = [i for i, c in enumerate(text) if c == ' ']
        if not spaces:
            return text
        idx = self.rng.choice(spaces)
        return text[:idx] + text[idx + 1:]

    def op_diacritic_remove(self, text: str) -> str:
        res = []
        for ch in text:
            low = ch.lower()
            if low in VIETNAMESE_ACCENTS_MAP:
                rep = VIETNAMESE_ACCENTS_MAP[low]
                res.append(rep.upper() if ch.isupper() else rep)
            else:
                res.append(ch)
        return "".join(res)

    def op_mixed_case(self, text: str) -> str:
        return "".join(
            c.upper() if self.rng.random() > 0.5 else c.lower()
            for c in text
        )

    def op_unicode_fullwidth(self, text: str) -> str:
        res = []
        for c in text:
            code = ord(c)
            if 0x21 <= code <= 0x7E:
                res.append(chr(code + 0xFEE0))
            elif code == 0x20:
                res.append(chr(0x3000))
            else:
                res.append(c)
        return "".join(res)

    def op_unicode_zerowidth(self, text: str) -> str:
        if not text:
            return text
        zw_chars = ["\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0"]
        idx = self.rng.randint(0, len(text))
        return text[:idx] + self.rng.choice(zw_chars) + text[idx:]

    def op_unicode_emoji(self, text: str) -> str:
        emojis = ["🔥", "📚", "🤖", "❓", "💡", "⚡", "🎓"]
        return text + " " + self.rng.choice(emojis)

    def op_punctuation_chaos(self, text: str) -> str:
        patterns = ["???", "!!!", "......", "???!!!", " ///// "]
        return text + self.rng.choice(patterns)

    def op_mixed_language(self, text: str) -> str:
        for p, rep in ENGLISH_VIETNAMESE_REPLACEMENTS:
            if re.search(p, text, re.IGNORECASE):
                return re.sub(p, rep, text, count=1, flags=re.IGNORECASE)
        return text

    def mutate(
        self,
        text: str,
        num_mutations: int = 1,
        allowed_ops: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        """
        Áp dụng ngẫu nhiên `num_mutations` toán tử đột biến lên văn bản đầu vào.
        """
        all_ops = {
            "char_delete": self.op_char_delete,
            "char_insert": self.op_char_insert,
            "char_substitute": self.op_char_substitute,
            "char_transpose": self.op_char_transpose,
            "space_insert": self.op_space_insert,
            "space_remove": self.op_space_remove,
            "diacritic_remove": self.op_diacritic_remove,
            "mixed_case": self.op_mixed_case,
            "unicode_fullwidth": self.op_unicode_fullwidth,
            "unicode_zerowidth": self.op_unicode_zerowidth,
            "unicode_emoji": self.op_unicode_emoji,
            "punctuation_chaos": self.op_punctuation_chaos,
            "mixed_language": self.op_mixed_language,
        }

        active_ops = allowed_ops or list(all_ops.keys())
        applied_ops = []
        current_text = text

        for _ in range(num_mutations):
            op_name = self.rng.choice(active_ops)
            fn = all_ops[op_name]
            mutated = fn(current_text)
            if mutated != current_text:
                current_text = mutated
                applied_ops.append(op_name)

        return current_text, applied_ops

    def shrink(
        self,
        seed_text: str,
        ops: List[str],
        check_func: Callable[[str], bool],
    ) -> Tuple[str, List[str]]:
        """
        Rút gọn tối thiểu chuỗi đột biến gây lỗi (Delta Debugging / Failure Minimization).
        Thử loại bỏ từng toán tử xem lỗi có còn xảy ra không.
        """
        minimal_ops = list(ops)
        all_ops_map = {
            "char_delete": self.op_char_delete,
            "char_insert": self.op_char_insert,
            "char_substitute": self.op_char_substitute,
            "char_transpose": self.op_char_transpose,
            "space_insert": self.op_space_insert,
            "space_remove": self.op_space_remove,
            "diacritic_remove": self.op_diacritic_remove,
            "mixed_case": self.op_mixed_case,
            "unicode_fullwidth": self.op_unicode_fullwidth,
            "unicode_zerowidth": self.op_unicode_zerowidth,
            "unicode_emoji": self.op_unicode_emoji,
            "punctuation_chaos": self.op_punctuation_chaos,
            "mixed_language": self.op_mixed_language,
        }

        # Thử loại bỏ từng op từ cuối lên
        for i in range(len(minimal_ops) - 1, -1, -1):
            candidate_ops = [op for j, op in enumerate(minimal_ops) if j != i]
            # Tái hiện chuỗi candidate
            curr = seed_text
            for op in candidate_ops:
                curr = all_ops_map[op](curr)
            if check_func(curr):
                # Vẫn gây lỗi -> loại bỏ op thứ i thành công
                minimal_ops = candidate_ops

        # Tính kết quả cuối cùng
        curr = seed_text
        for op in minimal_ops:
            curr = all_ops_map[op](curr)
        return curr, minimal_ops
