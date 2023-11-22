import math
from typing import Generator

import pytest
import torch

from outlines.generate.generator import (
    GenerationState,
    SequenceGenerator,
    bias_logits,
    expand_attention_masks,
    get_next_fsm_states,
    get_next_instructions,
    is_generation_finished,
    sequence_generator,
    token_generator,
    update_token_ids,
)
from outlines.index.index import FSMState


def test_sequence_generator_class():
    class MockFSM:
        def next_state(self, state, next_token_ids):
            return 0

        def next_instruction(self, _):
            return []

        def is_final_state(self, _):
            return True

    class MockTokenizer:
        def encode(self, _):
            return torch.tensor([[0, 1, 2, 3]]), torch.tensor([[1, 1, 1, 1]])

    class MockModel:
        def __init__(self):
            self.tokenizer = MockTokenizer()

        def __call__(*_):
            return torch.tensor([[0, 1, 2, 3]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, keepdims=True)

    # Stream
    generator = SequenceGenerator(MockFSM(), MockModel(), sampler, "cpu")
    assert generator.device == "cpu"
    assert isinstance(generator.tokenizer, MockTokenizer)
    assert isinstance(generator.fsm, MockFSM)
    assert callable(generator.generate_token)

    result = generator.init_generation_state("test")
    assert torch.equal(result.token_ids, torch.tensor([[0, 1, 2, 3]]))
    assert torch.equal(result.attention_masks, torch.tensor([[1, 1, 1, 1]]))
    assert result.kv_cache is None

    sequence = generator.stream("test")
    assert isinstance(sequence, Generator)

    state = next(sequence)
    assert torch.equal(state.token_ids, torch.tensor([[0, 1, 2, 3, 3]]))
    assert torch.equal(state.attention_masks, torch.tensor([[1, 1, 1, 1, 1]]))

    with pytest.raises(StopIteration):
        state = next(sequence)

    # Call
    generator = SequenceGenerator(MockFSM(), MockModel(), sampler, "cpu")
    result = generator("test")
    assert torch.equal(state.token_ids, torch.tensor([[0, 1, 2, 3, 3]]))
    assert torch.equal(state.attention_masks, torch.tensor([[1, 1, 1, 1, 1]]))


def test_sequence_generator_1d_single_iteration():
    class MockFSM:
        def next_state(self, state, next_token_ids):
            return 0

        def next_instruction(self, _):
            return []

        def is_final_state(self, _):
            return True

    class MockTokenizer:
        def encode(self, _):
            return torch.tensor([[0, 1, 2, 3]]), torch.tensor([[1, 1, 1, 1]])

    class MockModel:
        def __init__(self):
            self.tokenizer = MockTokenizer()

        def __call__(*_):
            return torch.tensor([[0, 1, 2, 3]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, keepdims=True)

    init_state = GenerationState(
        torch.tensor([[0, 1, 2, 3]]), torch.tensor([[1, 1, 1, 1]]), None
    )
    init_fsm_states = [0]
    generate = token_generator(MockModel(), sampler)
    sequence = sequence_generator(
        generate, MockFSM(), init_state, init_fsm_states, torch.Generator()
    )
    result = next(sequence)

    assert torch.equal(result.token_ids, torch.tensor([[0, 1, 2, 3, 3]]))
    assert torch.equal(result.attention_masks, torch.tensor([[1, 1, 1, 1, 1]]))

    with pytest.raises(StopIteration):
        next(sequence)


def test_sequence_generator_1d_several_iterations():
    class MockFSM:
        def next_state(self, state, next_token_ids):
            return FSMState(state + 1)

        def next_instruction(self, _):
            return []

        def is_final_state(self, state):
            if state < 2:
                return False
            else:
                return True

    class MockTokenizer:
        def encode(self, _):
            return torch.tensor([[0, 1, 2, 3]]), torch.tensor([[1, 1, 1, 1]])

    class MockModel:
        def __init__(self):
            self.tokenizer = MockTokenizer()

        def __call__(*_):
            return torch.tensor([[0, 1, 2, 3]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, keepdims=True)

    init_state = GenerationState(
        torch.tensor([[0, 1, 2, 3]]), torch.tensor([[1, 1, 1, 1]]), None
    )
    init_fsm_states = [0]
    generate = token_generator(MockModel(), sampler)
    sequence = sequence_generator(
        generate, MockFSM(), init_state, init_fsm_states, torch.Generator()
    )

    result = next(sequence)
    assert torch.equal(result.token_ids, torch.tensor([[0, 1, 2, 3, 3]]))
    assert torch.equal(result.attention_masks, torch.tensor([[1, 1, 1, 1, 1]]))

    result = next(sequence)
    assert torch.equal(result.token_ids, torch.tensor([[0, 1, 2, 3, 3, 3]]))
    assert torch.equal(result.attention_masks, torch.tensor([[1, 1, 1, 1, 1, 1]]))

    with pytest.raises(StopIteration):
        next(sequence)


def test_sequence_generator_2d_single_iteration():
    class MockFSM:
        def next_state(self, state, next_token_ids):
            return 0

        def next_instruction(self, _):
            return []

        def is_final_state(self, _):
            return True

    class MockTokenizer:
        def encode(self, _):
            return torch.tensor([[0, 1, 2, 3], [4, 5, 6, 7]]), torch.tensor(
                [[1, 1, 1, 1], [1, 1, 1, 1]]
            )

    class MockModel:
        def __init__(self):
            self.tokenizer = MockTokenizer()

        def __call__(*_):
            return torch.tensor([[0, 1, 2, 3], [4, 5, 7, 6]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, keepdims=True, dim=-1)

    init_state = GenerationState(
        torch.tensor([[0, 1, 2, 3], [4, 5, 6, 7]]),
        torch.tensor([[1, 1, 1, 1], [1, 1, 1, 1]]),
        None,
    )
    init_fsm_states = [0, 0]
    generate = token_generator(MockModel(), sampler)
    sequence = sequence_generator(
        generate, MockFSM(), init_state, init_fsm_states, torch.Generator()
    )

    result = next(sequence)
    assert torch.equal(
        result.token_ids, torch.tensor([[0, 1, 2, 3, 3], [4, 5, 6, 7, 2]])
    )
    assert torch.equal(
        result.attention_masks, torch.tensor([[1, 1, 1, 1, 1], [1, 1, 1, 1, 1]])
    )

    with pytest.raises(StopIteration):
        next(sequence)


def test_sequence_generator_2d_several_iterations():
    class MockFSM:
        def next_state(self, state, next_token_ids):
            return FSMState(state + 1)

        def next_instruction(self, _):
            return []

        def is_final_state(self, state):
            if state < 2:
                return False
            else:
                return True

    class MockTokenizer:
        def encode(self, _):
            return torch.tensor([[0, 1, 2, 3], [4, 5, 6, 7]]), torch.tensor(
                [[1, 1, 1, 1], [1, 1, 1, 1]]
            )

    class MockModel:
        def __init__(self):
            self.tokenizer = MockTokenizer()

        def __call__(*_):
            return torch.tensor([[0, 1, 2, 3], [4, 5, 7, 6]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, keepdims=True, dim=-1)

    init_state = GenerationState(
        torch.tensor([[0, 1, 2, 3], [4, 5, 6, 7]]),
        torch.tensor([[1, 1, 1, 1], [1, 1, 1, 1]]),
        None,
    )
    init_fsm_states = [0, 0]
    generate = token_generator(MockModel(), sampler)
    sequence = sequence_generator(
        generate, MockFSM(), init_state, init_fsm_states, torch.Generator()
    )

    result = next(sequence)
    assert torch.equal(
        result.token_ids, torch.tensor([[0, 1, 2, 3, 3], [4, 5, 6, 7, 2]])
    )
    assert torch.equal(
        result.attention_masks, torch.tensor([[1, 1, 1, 1, 1], [1, 1, 1, 1, 1]])
    )

    result = next(sequence)
    assert torch.equal(
        result.token_ids, torch.tensor([[0, 1, 2, 3, 3, 3], [4, 5, 6, 7, 2, 2]])
    )
    assert torch.equal(
        result.attention_masks, torch.tensor([[1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1]])
    )

    with pytest.raises(StopIteration):
        next(sequence)


def test_generator_error():
    def model(*_):
        raise IndexError

    def sampler():
        return None

    generator = token_generator(model, sampler)
    with pytest.raises(IndexError, match="The input length"):
        generator(None, None, None, None, None)


@pytest.mark.parametrize(
    "logits_biases,expected_result",
    [
        ([[]], [[3]]),
        ([[3]], [[2]]),
        ([[2, 3]], [[1]]),
    ],
)
def test_generator_1d(logits_biases, expected_result):
    def model(*_):
        return torch.tensor([[0, 1, 2, 3]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, keepdims=True)

    generator = token_generator(model, sampler)
    result, _ = generator(None, None, None, logits_biases, None)
    assert torch.equal(result, torch.tensor(expected_result))


@pytest.mark.parametrize(
    "logits_biases,expected_result",
    [
        ([[]], [[3], [3]]),
        ([[3], [3]], [[2], [2]]),
        ([[3], []], [[2], [3]]),
        ([[2, 3], [3]], [[1], [2]]),
    ],
)
def test_generator_2d(logits_biases, expected_result):
    def model(*_):
        return torch.tensor([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=torch.float), None

    def sampler(biased_logits, *_):
        return torch.argmax(biased_logits, dim=1, keepdims=True)

    generator = token_generator(model, sampler)
    result, _ = generator(None, None, None, logits_biases, None)
    assert torch.equal(result, torch.tensor(expected_result))


def test_get_next_fsm_states():
    class MockFSM:
        def next_state(self, state, next_token_ids):
            return 0

    result = get_next_fsm_states(MockFSM(), [0], torch.tensor([[0]]))
    assert result == [0]

    result = get_next_fsm_states(MockFSM(), [0, 0], torch.tensor([[0], [0]]))
    assert result == [0, 0]


def test_get_next_instructions():
    class MockFSM:
        def next_instruction(self, _):
            return [1, 2, 3, 4]

    result = get_next_instructions(MockFSM(), [0])
    assert result == [[1, 2, 3, 4]]

    result = get_next_instructions(MockFSM(), [0, 1])
    assert result == [[1, 2, 3, 4], [1, 2, 3, 4]]


def test_is_generation_finished():
    class MockFSMFinished:
        def is_final_state(self, _):
            return True

    result = is_generation_finished(MockFSMFinished(), [1, 1])
    assert result is True

    class MockFSMNotFinished:
        def is_final_state(self, state):
            if state == 0:
                return False
            else:
                return True

    result = is_generation_finished(MockFSMNotFinished(), [0, 1])
    assert result is False


@pytest.mark.parametrize(
    "token_ids,next_token_ids,expected_result",
    [
        (torch.tensor([[1]]), torch.tensor([[2]]), torch.tensor([[1, 2]])),
        (
            torch.tensor([[1], [1]]),
            torch.tensor([[2], [3]]),
            torch.tensor([[1, 2], [1, 3]]),
        ),
    ],
)
def test_update_token_ids(token_ids, next_token_ids, expected_result):
    result = update_token_ids(token_ids, next_token_ids)
    assert torch.equal(result, expected_result)


@pytest.mark.parametrize(
    "attention_masks,expected_result",
    [
        (
            torch.tensor([[1, 1]], dtype=torch.float),
            torch.tensor([[1, 1, 1]], dtype=torch.float),
        ),
        (
            torch.tensor([[1, 1], [1, 1]], dtype=torch.float),
            torch.tensor([[1, 1, 1], [1, 1, 1]], dtype=torch.float),
        ),
    ],
)
def test_expand_attention_masks(attention_masks, expected_result):
    result = expand_attention_masks(attention_masks)
    assert torch.equal(result, expected_result)


@pytest.mark.parametrize(
    "logits,indices_to_mask,expected",
    [
        (
            torch.tensor([[1, 2, 3, 4]], dtype=torch.float),
            [[]],
            torch.tensor([[1, 2, 3, 4]], dtype=torch.float),
        ),
        (
            torch.tensor([[1, 2, 3, 4]], dtype=torch.float),
            [[1]],
            torch.tensor([[1, -math.inf, 3, 4]], dtype=torch.float),
        ),
        (
            torch.tensor([[1, 2, 3, 4]], dtype=torch.float),
            [[1, 3]],
            torch.tensor([[1, -math.inf, 3, -math.inf]], dtype=torch.float),
        ),
        (
            torch.tensor([[1, 2, 3], [4, 5, 6]], dtype=torch.float),
            [[0], [2]],
            torch.tensor([[-math.inf, 2, 3], [4, 5, -math.inf]], dtype=torch.float),
        ),
        (
            torch.tensor([[1, 2, 3], [4, 5, 6]], dtype=torch.float),
            [[1], [0, 2]],
            torch.tensor(
                [[1, -math.inf, 3], [-math.inf, 5, -math.inf]], dtype=torch.float
            ),
        ),
    ],
)
def test_bias_logits(logits, indices_to_mask, expected):
    masked_logits = bias_logits(logits, indices_to_mask)
    assert torch.equal(masked_logits, expected)