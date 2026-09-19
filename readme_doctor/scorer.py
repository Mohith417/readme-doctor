import re

def parse_score(analysis_text):
    """Extract the numeric score from the AI analysis"""
    try:
        match = re.search(r'SCORE:\s*(\d+)', analysis_text)
        if match:
            score = int(match.group(1))
            return min(score, 100)  # cap at 100
    except:
        return 0
    return 0

def get_grade(score):
    """Convert numeric score to a letter grade"""
    if score >= 90:
        return "A", "Excellent README!"
    elif score >= 75:
        return "B", "Good README, minor improvements needed"
    elif score >= 60:
        return "C", "Average README, needs work"
    elif score >= 40:
        return "D", "Poor README, significant improvements needed"
    else:
        return "F", "Very poor README, needs complete rewrite"