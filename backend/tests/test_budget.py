import unittest

from backend.src.project.budget import Budget


class BudgetTests(unittest.TestCase):
    def test_moving_a_subtree_preserves_leaf_plans_and_updates_totals(self):
        root = Budget("Verbund")
        first_fund = Budget("Fördertopf A")
        second_fund = Budget("Fördertopf B")
        action = Budget("Aktion")
        project = Budget("Projekt")
        sibling = Budget("Weiteres Projekt")
        root.add_child(first_fund)
        root.add_child(second_fund)
        first_fund.add_child(action)
        action.add_child(project)
        action.add_child(sibling)
        project.set_plan(2026, {"personnel": 1200})
        sibling.set_plan(2026, {"personnel": 300})
        sibling.set_plan(2027, {"personnel": 500})

        self.assertEqual(first_fund.planned_total_cents(2026), 1500)
        second_fund.add_child(action)

        self.assertIs(action.parent, second_fund)
        self.assertEqual(project.node_path, (root.id, second_fund.id, action.id, project.id))
        self.assertEqual(first_fund.children, ())
        self.assertIn("personnel", first_fund.categories)
        self.assertEqual(first_fund.planned_total_cents(2026), 0)
        self.assertEqual(second_fund.planned_total_cents(2026), 1500)
        self.assertEqual(root.planned_total_cents(2027), 500)

    def test_cost_categories_are_independent_and_renaming_keeps_amounts(self):
        first = Budget("Projekt A")
        second = Budget("Projekt B")
        self.assertEqual(first.categories, {
            "personnel": "Personalkosten",
            "material": "Materialkosten",
            "other": "Sonstiges",
        })
        travel = first.add_category("Reisekosten")
        first.set_plan(2026, {"material": 300, travel: 200})
        first.rename_category("material", "Sachmittel")

        self.assertEqual(first.planned_costs(2026)["material"], 300)
        self.assertEqual(first.planned_costs(2026)["personnel"], 0)
        self.assertEqual(second.categories["material"], "Materialkosten")
        self.assertNotIn(travel, second.categories)
        first.set_plan(2026, {travel: 100})
        self.assertEqual(first.planned_total_cents(2026), 100)

    def test_branches_reject_categories_and_direct_plans(self):
        branch = Budget("Fördertopf")
        branch.add_child(Budget("Projekt"))

        self.assertEqual(branch.categories, {})
        with self.assertRaises(ValueError):
            branch.add_category("Reisekosten")
        with self.assertRaises(ValueError):
            branch.set_plan(2026, {"personnel": 100})

    def test_rejected_moves_keep_existing_parent_and_leaf_data(self):
        root = Budget("Verbund")
        project = Budget("Projekt")
        destination = Budget("Neuer Fördertopf")
        root.add_child(project)
        destination.set_plan(2026, {"material": 500})

        with self.assertRaises(ValueError):
            project.move_to(destination)
        self.assertEqual(destination.planned_total_cents(2026), 500)
        destination.set_plan(2026, {})
        destination.rename_category("material", "Sachmittel")
        with self.assertRaises(ValueError):
            project.move_to(destination)
        with self.assertRaises(ValueError):
            root.move_to(project)
        with self.assertRaises(ValueError):
            project.move_to(project)

        self.assertIs(project.parent, root)
        self.assertIsNone(root.parent)
        self.assertEqual(root.children, (project,))

    def test_rejected_duplicate_ids_keep_the_trees_separate(self):
        root = Budget("Verbund A")
        root.add_child(Budget("Projekt A", budget_id="shared"))
        other_root = Budget("Verbund B")
        other_root.add_child(Budget("Projekt B", budget_id="shared"))

        with self.assertRaises(ValueError):
            root.add_child(other_root)

        self.assertIsNone(other_root.parent)
        self.assertEqual(len(root.children), 1)
