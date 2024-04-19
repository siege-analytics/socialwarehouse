drop table CitEstPivot

drop table CvapPivot


SELECT * 

into CitEstPivot

FROM
 
(SELECT 
	geoname,
	geoid,
	lntitle,
	cit_est
FROM 
	[dbo].[BlockGr]
 )
AS CitEstTable
PIVOT(
	sum(cit_est)
	FOR lntitle IN ([Total],[Not Hispanic or Latino], [American Indian or Alaska Native Alone], [Asian Alone],
	 [Black or African American Alone], [Native Hawaiian or Other Pacific Islander Alone],
	 [White Alone], [American Indian or Alaska Native and White], [Asian and White], [Black or African American and White], 
	 [American Indian or Alaska Native and Black or African American], [Remainder of Two or More Race Responses],
	 [Hispanic or Latino])
)

 AS citestpivot

 order by geoid

 SELECT * 
 
 into CvapPivot

 FROM
 
(SELECT 
	geoname,
	geoid,
	lntitle,
	cvap_est
FROM 
	[dbo].[BlockGr]
 )
AS CvapTable
PIVOT(
	sum(cvap_est)
	FOR lntitle IN ([Total]
	,[Not Hispanic or Latino], [American Indian or Alaska Native Alone], [Asian Alone],
	 [Black or African American Alone], [Native Hawaiian or Other Pacific Islander Alone],
	 [White Alone], [American Indian or Alaska Native and White], [Asian and White], [Black or African American and White], 
	 [American Indian or Alaska Native and Black or African American], [Remainder of Two or More Race Responses],
	 [Hispanic or Latino])
)

 AS cvappivot

 order by geoid

 select CitEstPivot.geoname,
		CitEstPivot.geoid,
		CitEstPivot.Total as 'CitEst Total', 
		CitEstPivot.[Not Hispanic or Latino] as 'CitEst Not Hispanic or Latino',
		CitEstPivot.[American Indian or Alaska Native Alone] as 'CitEst American Indian or Alaska Native Alone', 
		CitEstPivot.[Asian Alone] as 'CitEst Asian Alone',
		CitEstPivot.[Black or African American Alone] as 'CitEst Black or African American Alone',
		CitEstPivot.[Native Hawaiian or Other Pacific Islander Alone] as 'CitEst Native Hawaiian or Other Pacific Islander Alone',
		CitEstPivot.[White Alone] as 'CitEst White Alone',
		CitEstPivot.[American Indian or Alaska Native and White] as 'CitEst American Indian or Alaska Native and White',
		CitEstPivot.[Asian and White] as 'CitEst Asian and White',
		CitEstPivot.[Black or African American and White] as 'CitEst Black or African American and White', 
		CitEstPivot.[American Indian or Alaska Native and Black or African American] as 'CitEst American Indian or Alaska Native and Black or African American',
		CitEstPivot.[Remainder of Two or More Race Responses] as 'CitEst Remainder of Two or More Race Responses',
		CitEstPivot.[Hispanic or Latino] as 'CitEst Hispanic or Latino', CvapPivot.Total as 'CVAP Total', 
		CvapPivot.[Not Hispanic or Latino] as 'CVAP Not Hispanic or Latino',
		CvapPivot.[American Indian or Alaska Native Alone] as 'CVAP American Indian or Alaska Native Alone', 
		CvapPivot.[Asian Alone] as 'CVAP Asian Alone',
		CvapPivot.[Black or African American Alone] as 'CVAP Black or African American Alone',
		CvapPivot.[Native Hawaiian or Other Pacific Islander Alone] as 'CVAP Native Hawaiian or Other Pacific Islander Alone',
		CvapPivot.[White Alone] as 'CVAP White Alone',
		CvapPivot.[American Indian or Alaska Native and White] as 'CVAP American Indian or Alaska Native and White',
		CvapPivot.[Asian and White] as 'CVAP Asian and White',
		CvapPivot.[Black or African American and White] as 'CVAP Black or African American and White', 
		CvapPivot.[American Indian or Alaska Native and Black or African American] as 'CVAP American Indian or Alaska Native and Black or African American',
		CvapPivot.[Remainder of Two or More Race Responses] as 'CVAP Remainder of Two or More Race Responses',
		CvapPivot.[Hispanic or Latino] as 'CVAP Hispanic or Latino'
From CvapPivot

 left join CitEstPivot

 on CvapPivot.geoid = CitEstPivot.geoid

 order by CitEstPivot.geoid