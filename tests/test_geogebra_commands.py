import json
from pathlib import Path
import unittest

from tools.geometry.construction_tool import prepare_geometry
from geometry3d.geogebra import SpecError, compile_construction, validate_spec


FIXTURES = Path(__file__).parent / 'fixtures' / 'geogebra'


def integral():
    return json.loads((FIXTURES / 'integral-region.json').read_text())


class DocumentedCommandTests(unittest.TestCase):
    def test_integral_region_is_an_executable_command_and_keeps_its_fill(self):
        result = prepare_geometry(integral())
        self.assertEqual(result['status'], 'prepared', result)
        step = result['artifact']['steps'][-1]
        self.assertEqual(step['commands'], ['region=IntegralBetween(g,f,-1.0,2.0)'])
        self.assertEqual(step['expected_labels'], ['region'])
        self.assertEqual(result['artifact']['spec']['steps'][-1]['fill_opacity'], 0.5)

    def test_same_command_path_constructs_other_documented_objects(self):
        raw = {'version':1,'title':'Cone and circle','app':'3d','steps':[
            {'id':'O','op':'point','coords':[0,0,0]},
            {'id':'S','op':'point','coords':[0,0,4]},
            {'id':'cone','op':'command','name':'Cone','args':[{'ref':'O'},{'ref':'S'},{'number':2}]},
            {'id':'base','op':'command','name':'Circle','args':[{'ref':'O'},{'number':2}]},
        ]}
        result = prepare_geometry(raw)
        self.assertEqual(result['status'], 'prepared', result)
        self.assertEqual(result['artifact']['steps'][-2]['commands'], ['cone=Cone(O,S,2.0)'])
        self.assertEqual(result['artifact']['steps'][-1]['commands'], ['base=Circle(O,2.0)'])

    def test_documented_command_arguments_keep_dependencies(self):
        raw = integral()
        raw['steps'] = [raw['steps'][-1], *raw['steps'][:2]]
        artifact = compile_construction(validate_spec(raw))
        self.assertEqual(artifact.steps[-1].source_step_id, 'region')
        raw['steps'][0]['args'][0]['ref'] = 'missing'
        with self.assertRaises(SpecError) as error:
            validate_spec(raw)
        self.assertEqual(error.exception.code, 'missing_reference')

    def test_unknown_scripting_and_injected_commands_are_rejected(self):
        for name in ('FakeUnknownShape', 'Execute', 'Delete', 'SetValue', 'IntegralBetween);Delete(f'):
            with self.subTest(name=name):
                raw = integral()
                raw['steps'][-1]['name'] = name
                self.assertEqual(prepare_geometry(raw)['status'], 'invalid_spec')

    def test_expression_boolean_and_list_arguments_compile_without_raw_code(self):
        raw = integral()
        raw['steps'][-1] = {'id':'values','op':'command','name':'Append','args':[
            {'items':[{'number':1},{'expression':'sqrt(2)'}]}, {'boolean':True},
        ]}
        result = prepare_geometry(raw)
        self.assertEqual(result['status'], 'prepared', result)
        self.assertEqual(result['artifact']['steps'][-1]['commands'], ['values=Append({1.0,sqrt(2)},true)'])
        raw['steps'][-1]['args'][0]['items'][1]['expression'] = 'Delete(f)'
        self.assertEqual(prepare_geometry(raw)['status'], 'invalid_spec')


if __name__ == '__main__':
    unittest.main()
