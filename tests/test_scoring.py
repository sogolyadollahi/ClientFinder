from app.scoring import calculate_score

def test_relevant_agency_scores_higher():
    strong = calculate_score(
        "n8n automation, CRM, API integration, Python",
        "We are hiring a remote freelance Python developer",
        company_size="small",
        has_public_contact=True,
    )
    weak = calculate_score("Graphic design studio", "Contact us", company_size="unknown")
    assert strong.score > weak.score
    assert 0 <= strong.score <= 100

def test_empty_information_scores_zero():
    result = calculate_score("", "")
    assert result.score == 0
    assert result.reasons == []

def test_score_is_capped_at_100():
    result = calculate_score(
        "automation workflow automation n8n make.com zapier crm hubspot salesforce api integration ai integration python software development",
        "we are hiring careers join our team freelance contractor remote internship backend developer python developer",
        company_size="small",
        has_public_contact=True,
    )
    assert result.score <= 100
