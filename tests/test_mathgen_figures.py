import base64
import copy
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from server.adapter import adapt_payload
from server.convert_cli import resolve_figures


class MathgenFigureTests(unittest.TestCase):
    def test_v2_figures_reach_parser_as_embedded_images(self):
        png = io.BytesIO()
        Image.new('RGB', (800, 400), 'white').save(png, format='PNG')
        figure = {'type': 'figure', 'crop': 'data:image/png;base64,' + base64.b64encode(png.getvalue()).decode()}
        source = {'renderFigures': True, 'problems': [{'number': 8, 'contents': [figure],
            'choices': [{'number': 1, 'contents': [figure]}],
            'subQuestions': [{'number': 1, 'contents': [figure], 'score': '3.0'}]}]}
        original = copy.deepcopy(source)
        envelope, _, _ = adapt_payload(source)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(resolve_figures(envelope, Path(folder)), 0)
            q = envelope['questions'][0]
            for block in [q['contents'][0], q['choices'][0]['contents'][0], q['sub_questions'][0]['contents'][0]]:
                self.assertEqual(block['type'], 'image')
                with Image.open(block['value']) as image:
                    self.assertEqual(image.size, (800, 400))
            self.assertEqual(q['sub_questions'][0]['score'], '3.0')
        self.assertEqual(source, original)

    def test_corrupt_crop_and_filesystem_image_do_not_cross_boundary(self):
        envelope, _, _ = adapt_payload({'problems': [{'number': 1, 'contents': [
            {'type': 'image', 'value': 'C:/private.png'}, {'type': 'figure', 'crop': 'not base64'}]}]})
        self.assertEqual(len(envelope['questions'][0]['contents']), 1)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(resolve_figures(envelope, Path(folder)), 1)
            self.assertFalse(list(Path(folder).glob('*.png')))


if __name__ == '__main__':
    unittest.main()
