import uuid
from datetime import datetime

class FHIRConceptMap:
    @staticmethod
    def create_conceptmap(mappings):
        """Create FHIR ConceptMap for NAMASTE to ICD-11 mapping"""
        return {
            "resourceType": "ConceptMap",
            "id": str(uuid.uuid4()),
            "url": "http://namaste.gov.in/fhir/ConceptMap/namaste-to-icd11",
            "version": "1.0.0",
            "name": "NAMASTEToICD11Map",
            "title": "NAMASTE to ICD-11 Concept Map",
            "status": "active",
            "date": datetime.now().isoformat(),
            "publisher": "NAMASTE Initiative",
            "description": "Mapping from NAMASTE traditional medicine codes to ICD-11 codes",
            "sourceUri": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
            "targetUri": "http://id.who.int/icd/release/11/mms",
            "group": [
                {
                    "source": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
                    "target": "http://id.who.int/icd/release/11/mms",
                    "element": [
                        {
                            "code": mapping['source_code'],
                            "display": mapping['source_display'],
                            "target": [
                                {
                                    "code": mapping['target_code'],
                                    "display": mapping['target_display'],
                                    "equivalence": mapping['equivalence']
                                }
                            ] if mapping['target_code'] != 'unmapped' else []
                        }
                        for mapping in mappings
                    ]
                }
            ]
        }
    
    @staticmethod
    def create_translation_response(source_code, source_display, target_mappings):
        """Create FHIR Parameters resource for translation response"""
        parameters = [
            {
                "name": "result",
                "valueBoolean": len(target_mappings) > 0
            },
            {
                "name": "message",
                "valueString": "Translation successful" if target_mappings else "No mapping found"
            }
        ]
        
        for mapping in target_mappings:
            parameters.append({
                "name": "match",
                "part": [
                    {
                        "name": "equivalence",
                        "valueCode": mapping['equivalence']
                    },
                    {
                        "name": "concept",
                        "valueCoding": {
                            "system": "http://id.who.int/icd/release/11/mms",
                            "code": mapping['target_code'],
                            "display": mapping['target_display']
                        }
                    }
                ]
            })
        
        return {
            "resourceType": "Parameters",
            "id": str(uuid.uuid4()),
            "parameter": parameters
        }

class ConceptMapper:
    def __init__(self, namaste_service, icd_search_func):
        self.namaste_service = namaste_service
        self.icd_search = icd_search_func
        self.mappings = self._create_mappings()
    
    def _create_mappings(self):
        """Create predefined mappings between NAMASTE and ICD-11"""
        return {
            'NAM-AYU-002': {'search_term': 'fever', 'equivalence': 'equivalent'},
            'NAM-AYU-008': {'search_term': 'fever', 'equivalence': 'equivalent'},
            'NAM-UNA-001': {'search_term': 'fever', 'equivalence': 'equivalent'},
            'NAM-SID-001': {'search_term': 'fever', 'equivalence': 'equivalent'},
            'NAM-HOM-001': {'search_term': 'fever', 'equivalence': 'equivalent'},
            'NAM-AYU-003': {'search_term': 'cough', 'equivalence': 'equivalent'},
            'NAM-UNA-002': {'search_term': 'cough', 'equivalence': 'equivalent'},
            'NAM-SID-002': {'search_term': 'cough', 'equivalence': 'equivalent'},
            'NAM-HOM-002': {'search_term': 'cough', 'equivalence': 'equivalent'},
            'NAM-AYU-004': {'search_term': 'diabetes', 'equivalence': 'equivalent'},
            'NAM-UNA-003': {'search_term': 'diabetes', 'equivalence': 'equivalent'},
            'NAM-SID-003': {'search_term': 'diabetes', 'equivalence': 'equivalent'},
            'NAM-HOM-003': {'search_term': 'diabetes', 'equivalence': 'equivalent'}
        }
    
    def translate_code(self, namaste_code):
        """Translate NAMASTE code to ICD-11"""
        # Get NAMASTE code details
        namaste_concept = None
        csv_data = getattr(self.namaste_service, 'csv_data', [])
        for row in csv_data:
            if row.get('code') == namaste_code:
                namaste_concept = row
                break
        
        if not namaste_concept:
            return []
        
        # Check if mapping exists
        if namaste_code in self.mappings:
            mapping_info = self.mappings[namaste_code]
            icd_results = self.icd_search(mapping_info['search_term'])
            
            if icd_results:
                # Return first matching ICD-11 code (clean HTML tags)
                display_name = icd_results[0]['name']
                # Remove HTML tags
                import re
                clean_name = re.sub(r'<[^>]+>', '', display_name)
                
                return [{
                    'target_code': icd_results[0]['code'],
                    'target_display': clean_name,
                    'equivalence': mapping_info['equivalence']
                }]
        
        return []  # No mapping found
    
    def get_all_mappings(self):
        """Get all NAMASTE to ICD-11 mappings"""
        all_mappings = []
        
        csv_data = getattr(self.namaste_service, 'csv_data', [])
        for row in csv_data:
            namaste_code = row['code']
            target_mappings = self.translate_code(namaste_code)
            
            if target_mappings:
                for target in target_mappings:
                    all_mappings.append({
                        'source_code': namaste_code,
                        'source_display': row['name'],
                        'target_code': target['target_code'],
                        'target_display': target['target_display'],
                        'equivalence': target['equivalence']
                    })
            else:
                all_mappings.append({
                    'source_code': namaste_code,
                    'source_display': row['name'],
                    'target_code': 'unmapped',
                    'target_display': 'No mapping available',
                    'equivalence': 'unmatched'
                })
        
        return all_mappings