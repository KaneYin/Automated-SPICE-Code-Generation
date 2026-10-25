"""Character-span attribution without pretending characters are model tokens."""
import hashlib
import json
from pathlib import Path


def text_content(message):
    content = message.get('content', '')
    if isinstance(content, list):
        return '\n'.join(b.get('text', '') for b in content if b.get('type') == 'text')
    return content


def template_spans(text):
    """Partition known prompt sections without changing any rendered characters.

    Unrecognized templates retain an explicitly unseparated category. These are
    structural character spans, not a claim about the server's evaluated tokens.
    """
    question = text.rfind('## Question')
    if question < 0 or 'Input node name:' not in text[question:]:
        return [(0, len(text), 'template_and_task_unseparated')]
    answer = text.find('## Answer', question)
    intervals = [(question, answer if answer >= 0 else len(text), 'task_specification')]
    example = text.find('Here is an example:')
    example_end = text.find('As you have seen', example) if example >= 0 else -1
    if 0 <= example < example_end <= question:
        intervals.append((example, example_end, 'examples'))
    background = text.find('\n\nHint Background: \n')
    if background >= 0:
        intervals.insert(0, (background, len(text), 'retrieved_background'))
    boundaries = sorted({0, len(text), *(x for a, b, _ in intervals for x in (a, b))})
    return [(a, b, next((label for lo, hi, label in intervals if lo <= a and b <= hi),
                       'template_instructions')) for a, b in zip(boundaries, boundaries[1:]) if b > a]


def message_components(messages, phase='unknown'):
    result = []
    for i, message in enumerate(messages):
        role = message.get('role')
        content = text_content(message)
        category = ('system_instructions' if role == 'system' else
                    'prior_assistant_responses' if role == 'assistant' else
                    'waveform_text' if phase == 'waveform_analysis' else
                    'latest_diagnostics' if i == len(messages) - 1 and phase == 'repair_generation' else
                    'prior_feedback' if any(m.get('role') == 'assistant' for m in messages[:i]) else
                    'template_and_task_unseparated')
        spans = template_spans(content) if category == 'template_and_task_unseparated' else [(0, len(content), category)]
        for start, end, label in spans:
            result.append({'message_index': i, 'start': start, 'end': end, 'category': label,
                           'tokens': None, 'quality': 'unavailable', 'method': 'character_span',
                           'tokenizer': None, 'chat_template': None,
                           'unknown_reason': 'Matching tokenizer and evaluated prompt mapping not verified'})
        if message.get('images') or isinstance(message.get('content'), list) and any(
                b.get('type') == 'image_url' for b in message['content']):
            result.append({'message_index': i, 'category': 'image', 'tokens': None,
                           'quality': 'unavailable', 'method': 'provider_image_processing'})
    return result


def validate_spans(messages, spans):
    ends = {}
    for span in sorted((s for s in spans if 'start' in s), key=lambda s: (s['message_index'], s['start'])):
        i = span['message_index']
        text = text_content(messages[i])
        if not 0 <= span['start'] <= span['end'] <= len(text):
            raise ValueError('Invalid component span')
        if span['start'] < ends.get(i, 0):
            raise ValueError('Overlapping component spans')
        ends[i] = span['end']


def attribute_with_tokenizer(messages, spans, tokenizer, provider_input_tokens):
    """Optional per-string tokenizer interface. Counts are estimates, never exact."""
    validate_spans(messages, spans)
    counted = []
    for span in spans:
        item = dict(span)
        if 'start' in item:
            text = text_content(messages[item['message_index']])[item['start']:item['end']]
            item.update(tokens=len(tokenizer.encode(text)), quality='estimated',
                        method='per_string_tokenizer', tokenizer=tokenizer.identity,
                        chat_template=getattr(tokenizer, 'chat_template', None))
        counted.append(item)
    observed = sum(s['tokens'] for s in counted if s.get('tokens') is not None)
    return {'components': counted, 'reconciliation_difference':
            provider_input_tokens - observed if provider_input_tokens is not None else None,
            'quality': 'estimated', 'evaluated_prompt_mapping': 'unverified'}


def load_tokenizer(path):
    """Optional local tokenizer.json, pinned to a digest; never downloads assets.

    A user-supplied digest binding verifies file identity, not provider equivalence.
    Per-string counts remain estimates even when these checks pass.
    """
    if path is None:
        return None
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    for key in ('identity', 'model_digest', 'tokenizer_json', 'sha256'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError('Tokenizer configuration requires ' + key)
    asset = (path.parent / config['tokenizer_json']).resolve()
    if hashlib.sha256(asset.read_bytes()).hexdigest() != config['sha256']:
        raise ValueError('Tokenizer asset checksum mismatch')
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise RuntimeError('Optional tokenizer estimates require the tokenizers package and a local tokenizer.json') from exc
    class LocalTokenizer:
        identity = config['identity']
        model_digest = config['model_digest']
        chat_template = config.get('chat_template_identity')
        provenance = dict(config, tokenizer_json=str(asset), config_path=str(path))
        def __init__(self):
            self.encoder = Tokenizer.from_file(str(asset))
        def encode(self, text):
            return self.encoder.encode(text, add_special_tokens=False).ids
    return LocalTokenizer()
