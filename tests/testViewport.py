import unittest
from PyQt5.QtWidgets import QApplication
from src.viewport import Viewport

class TestViewport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([])

    def setUp(self):
        self.parent = None
        self._id = 1
        self.view_dir = type('ViewDir', (object,), {'dir': 'AX'})  # Mock view direction
        self.num_vols = 3
        self.paint_method = lambda x: x
        self.erase_method = lambda x: x
        self.mark_method = lambda x: x
        self.zoom_method = lambda x: x
        self.pan_method = lambda x: x
        self.window_method = lambda x: x
        self.alpha_blending = False

    def test_constructor(self):
        viewport = Viewport(
            self.parent, self._id, self.view_dir, self.num_vols,
            self.paint_method, self.erase_method, self.mark_method,
            self.zoom_method, self.pan_method, self.window_method,
            self.alpha_blending
        )

        self.assertEqual(viewport.parent, self.parent)
        self.assertEqual(viewport.id, self._id)
        self.assertEqual(viewport.view_dir, self.view_dir.dir)
        self.assertEqual(viewport.num_vols_allowed, self.num_vols)
        self.assertEqual(viewport.paint_im, self.paint_method)
        self.assertEqual(viewport.erase_im, self.erase_method)
        self.assertEqual(viewport.mark_im, self.mark_method)
        self.assertEqual(viewport.zoom_im, self.zoom_method)
        self.assertEqual(viewport.pan_im, self.pan_method)
        self.assertEqual(viewport.window_im, self.window_method)
        self.assertIsNone(viewport.interaction_state)

    @classmethod
    def tearDownClass(cls):
        cls.app.quit()

if __name__ == '__main__':
    unittest.main()
