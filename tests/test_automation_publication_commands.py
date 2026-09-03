import unittest

from ai_product_photo_sorter.automation_cli import build_parser


class AutomationPublicationCommandTests(unittest.TestCase):
    def test_publication_commands_require_request_and_reservation(self):
        parser = build_parser()
        for command in ("execute-shopify-publish", "execute-shopify-rollback"):
            with self.subTest(command=command):
                args = parser.parse_args([command, "request.json", "reservation.json"])
                self.assertEqual(args.command, command)

    def test_no_bare_publish_command(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["publish"])


if __name__ == "__main__":
    unittest.main()
