import uuid
from datetime import datetime

class FHIRCodeSystem:
    @staticmethod
    def create_namaste_codesystem(concepts):
        """Create FHIR CodeSystem for NAMASTE codes"""
        return {
            "resourceType": "CodeSystem",
            "id": str(uuid.uuid4()),
            "url": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
            "version": "1.0.0",
            "name": "NAMASTECodes",
            "title": "NAMASTE Traditional Medicine Codes",
            "status": "active",
            "date": datetime.now().isoformat(),
            "publisher": "NAMASTE Initiative",
            "description": "Traditional medicine codes from AYUSH systems",
            "content": "complete",
            "count": len(concepts),
            "concept": [
                {
                    "code": concept['code'],
                    "display": concept['name'],
                    "definition": concept['description'],
                    "property": [
                        {
                            "code": "system",
                            "valueString": concept['system']
                        }
                    ]
                }
                for concept in concepts
            ]
        }
    
    @staticmethod
    def create_icd11_codesystem(concepts):
        """Create FHIR CodeSystem for ICD-11 codes"""
        return {
            "resourceType": "CodeSystem",
            "id": str(uuid.uuid4()),
            "url": "http://id.who.int/icd/release/11/mms",
            "version": "2022-02",
            "name": "ICD11MMS",
            "title": "ICD-11 Mortality and Morbidity Statistics",
            "status": "active",
            "date": datetime.now().isoformat(),
            "publisher": "World Health Organization",
            "description": "International Classification of Diseases 11th Revision",
            "content": "fragment",
            "count": len(concepts),
            "concept": [
                {
                    "code": concept['code'],
                    "display": concept['name']
                }
                for concept in concepts
            ]
        }
    
    @staticmethod
    def create_search_valueset(query, namaste_concepts, icd11_concepts):
        """Create FHIR ValueSet for search results"""
        return {
            "resourceType": "ValueSet",
            "id": str(uuid.uuid4()),
            "url": f"http://namaste.gov.in/fhir/ValueSet/search-{query}",
            "version": "1.0.0",
            "name": f"SearchResults{query.title()}",
            "title": f"Search Results for '{query}'",
            "status": "active",
            "date": datetime.now().isoformat(),
            "description": f"Combined search results for query: {query}",
            "compose": {
                "include": [
                    {
                        "system": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
                        "concept": [
                            {
                                "code": concept['code'],
                                "display": concept['name']
                            }
                            for concept in namaste_concepts
                        ]
                    },
                    {
                        "system": "http://id.who.int/icd/release/11/mms",
                        "concept": [
                            {
                                "code": concept['code'],
                                "display": concept['name']
                            }
                            for concept in icd11_concepts
                        ]
                    }
                ]
            },
            "expansion": {
                "timestamp": datetime.now().isoformat(),
                "total": len(namaste_concepts) + len(icd11_concepts),
                "contains": [
                    {
                        "system": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
                        "code": concept['code'],
                        "display": concept['name']
                    }
                    for concept in namaste_concepts
                ] + [
                    {
                        "system": "http://id.who.int/icd/release/11/mms",
                        "code": concept['code'],
                        "display": concept['name']
                    }
                    for concept in icd11_concepts
                ]
            }
        }