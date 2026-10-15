# Stock-to-FMF workbench parity

Generated command coverage baseline. Commands not pinned in FMF remain available through
FreeCAD's native menus and command search when a live QAction was observed. Source-only
literals are retained as intentional omissions until the supported host exposes an
action.

## PartDesignWorkbench

- FMF commands: 58
- Source command literals: 55
- Not in FMF layout: 26

- Live actions after activation: 279
- Searchable/native-menu dispositions: 16
- Intentional source-only omissions: 10
- Activation time: 534.278 ms

### Verified dispositions

- **Searchable/native menu:** `PartDesign_CompPrimitiveAdditive` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_CompSketches` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_DuplicateSelection` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_InvoluteGear` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_LinearPattern` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_MultiTransform` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_PolarPattern` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_Sprocket` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `PartDesign_WizardShaft` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_ColorPerFace` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_CoordinateSystem` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_DatumLine` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_DatumPlane` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_DatumPoint` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_MirrorSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Std_RandomColor` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Intentional omission:** `PartDesign_CircularPattern` — no QAction appeared after activating this workbench; use the pinned PartDesign_PolarPattern command.
- **Intentional omission:** `PartDesign_Defeaturing` — no QAction appeared after activating this workbench; use searchable Part_Defeaturing in the Part workbench.
- **Intentional omission:** `PartDesign_MoveFeature` — no QAction appeared after activating this workbench; use the native selection-dependent tree context menu.
- **Intentional omission:** `PartDesign_MoveFeatureInTree` — no QAction appeared after activating this workbench; use the native selection-dependent tree context menu.
- **Intentional omission:** `PartDesign_MoveTip` — no QAction appeared after activating this workbench; use the native Body tree context menu.
- **Intentional omission:** `PartDesign_PathPattern` — no QAction appeared after activating this workbench; not exposed as a QAction by this supported source build.
- **Intentional omission:** `PartDesign_PointPattern` — no QAction appeared after activating this workbench; not exposed as a QAction by this supported source build.
- **Intentional omission:** `Part_Box_Parametric` — no QAction appeared after activating this workbench; use the FMF primitive/create path.
- **Intentional omission:** `Std_DuplicateSelection` — no QAction appeared after activating this workbench; use searchable PartDesign_DuplicateSelection.
- **Intentional omission:** `Std_ToggleFreeze` — no QAction appeared after activating this workbench; use the native selection-dependent tree context menu.

### FMF inventory

- `FMF_CreateSketch`
- `FMF_DatumMidplane`
- `FMF_Export`
- `FMF_Export3MF`
- `FMF_ExportDXF`
- `FMF_ExportSTEP`
- `FMF_ExportSTL`
- `FMF_ParameterDock`
- `FMF_ParameterTable`
- `FMF_Reapply`
- `FMF_RepairReferences`
- `FMF_Restore`
- `FMF_StudioViewport`
- `FMF_UpdateModel`
- `FMF_Verify`
- `FMF_MoreCreate_ddb`
- `FMF_Pattern_ddb`
- `PartDesign_AdditiveHelix`
- `PartDesign_AdditiveLoft`
- `PartDesign_AdditivePipe`
- `PartDesign_Body`
- `PartDesign_Boolean`
- `PartDesign_Chamfer`
- `PartDesign_Clone`
- `PartDesign_CompPrimitiveSubtractive`
- `PartDesign_CoordinateSystem`
- `PartDesign_Draft`
- `PartDesign_Fillet`
- `PartDesign_Groove`
- `PartDesign_Hole`
- `PartDesign_Line`
- `PartDesign_Mirrored`
- `PartDesign_NewSketch`
- `PartDesign_Pad`
- `PartDesign_Plane`
- `PartDesign_Pocket`
- `PartDesign_Point`
- `PartDesign_Revolution`
- `PartDesign_Scaled`
- `PartDesign_ShapeBinder`
- `PartDesign_SubShapeBinder`
- `PartDesign_SubtractiveHelix`
- `PartDesign_SubtractiveLoft`
- `PartDesign_SubtractivePipe`
- `PartDesign_Thickness`
- `Part_CheckGeometry`
- `Sketcher_EditSketch`
- `Sketcher_MapSketch`
- `Sketcher_MergeSketches`
- `Sketcher_ReorientSketch`
- `Sketcher_ValidateSketch`
- `Std_BoxElementSelection`
- `Std_BoxSelection`
- `Std_Measure`
- `Std_Properties`
- `Std_UnitsCalculator`
- `Std_ViewFitAll`
- `Std_WhatsThis`

## PartWorkbench

- FMF commands: 62
- Source command literals: 60
- Not in FMF layout: 12

- Live actions after activation: 343
- Searchable/native-menu dispositions: 11
- Intentional source-only omissions: 1
- Activation time: 90.244 ms

### Verified dispositions

- **Searchable/native menu:** `Part_BoxSelection` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_CompCompoundTools` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_CompSplitFeatures` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_EditAttachment` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_JoinConnect` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_JoinCutout` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_JoinEmbed` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_Offset` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_Offset2D` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Part_Tube` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Std_RandomColor` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Intentional omission:** `Part_LinkArrays` — no QAction appeared after activating this workbench; use the searchable native array commands exposed by the group.

### FMF inventory

- `FMF_Export`
- `FMF_Export3MF`
- `FMF_ExportDXF`
- `FMF_ExportSTEP`
- `FMF_ExportSTL`
- `FMF_RepairReferences`
- `FMF_UpdateModel`
- `Part_Boolean`
- `Part_BooleanFragments`
- `Part_Box`
- `Part_Builder`
- `Part_Chamfer`
- `Part_CheckGeometry`
- `Part_ColorPerFace`
- `Part_Common`
- `Part_CompJoinFeatures`
- `Part_CompOffset`
- `Part_Compound`
- `Part_CompoundFilter`
- `Part_Cone`
- `Part_CrossSections`
- `Part_Cut`
- `Part_Cylinder`
- `Part_Defeaturing`
- `Part_ElementCopy`
- `Part_ExplodeCompound`
- `Part_Extrude`
- `Part_Fillet`
- `Part_Fuse`
- `Part_Loft`
- `Part_MakeFace`
- `Part_MakeSolid`
- `Part_Mirror`
- `Part_PointsFromMesh`
- `Part_Primitives`
- `Part_ProjectionOnSurface`
- `Part_RefineShape`
- `Part_ReverseShape`
- `Part_Revolve`
- `Part_RuledSurface`
- `Part_Scale`
- `Part_Section`
- `Part_SectionCut`
- `Part_ShapeFromMesh`
- `Part_SimpleCopy`
- `Part_Slice`
- `Part_SliceApart`
- `Part_Sphere`
- `Part_Sweep`
- `Part_Thickness`
- `Part_ToleranceSet`
- `Part_Torus`
- `Part_TransformedCopy`
- `Part_XOR`
- `Sketcher_NewSketch`
- `Std_BoxElementSelection`
- `Std_BoxSelection`
- `Std_Measure`
- `Std_Properties`
- `Std_UnitsCalculator`
- `Std_ViewFitAll`
- `Std_WhatsThis`

## SketcherWorkbench

- FMF commands: 83
- Source command literals: 122
- Not in FMF layout: 56

- Live actions after activation: 459
- Searchable/native-menu dispositions: 51
- Intentional source-only omissions: 5
- Activation time: 121.686 ms

### Verified dispositions

- **Searchable/native menu:** `Sketcher_BSplineDecreaseKnotMultiplicity` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_BSplineIncreaseKnotMultiplicity` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CompCreateArc` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CompCreateRegularPolygon` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CompHorVer` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainAngle` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainDiameter` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainDistance` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainDistanceX` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainDistanceY` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainGroup` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainHorizontal` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainLock` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainRadiam` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainRadius` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainSnellsLaw` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ConstrainVertical` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_Create3PointArc` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_Create3PointCircle` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateArcOfEllipse` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateArcOfHyperbola` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateArcOfParabola` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateArcSlot` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateBSplineByInterpolation` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateChamfer` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateCircle` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateEllipseBy3Points` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateEllipseByCenter` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateFillet` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateHeptagon` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateHexagon` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateOblong` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateOctagon` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreatePentagon` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreatePeriodicBSpline` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreatePeriodicBSplineByInterpolation` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateRegularPolygon` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateSquare` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_CreateTriangle` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_EditSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_MapSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_MergeSketches` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_MirrorSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_NewSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_Projection` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ReorientSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_Split` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_StopOperation` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ValidateSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ViewSection` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Searchable/native menu:** `Sketcher_ViewSketch` — deliberately not pinned; the live native action remains available without weakening FMF's curated layout.
- **Intentional omission:** `Sketcher_CompConstrainRadDia` — no QAction appeared after activating this workbench; use the pinned context-sensitive Sketcher_Dimension command.
- **Intentional omission:** `Sketcher_ConstrainCoincident` — no QAction appeared after activating this workbench; use pinned Sketcher_ConstrainCoincidentUnified, which dispatches Coincident or Point-on-object from the current selection.
- **Intentional omission:** `Sketcher_ConstrainPointOnObject` — no QAction appeared after activating this workbench; use pinned Sketcher_ConstrainCoincidentUnified.
- **Intentional omission:** `Sketcher_CreateDraftLine` — no QAction appeared after activating this workbench; the host source comments this command out.
- **Intentional omission:** `Sketcher_ProfilesHexagon1` — no QAction appeared after activating this workbench; use the searchable regular-polygon/profile commands.

### FMF inventory

- `FMF_AddMidline`
- `FMF_ConstrainMidpoint`
- `FMF_CreateSketch`
- `FMF_CreateSlot`
- `FMF_MirrorWithConstraints`
- `FMF_RepairReferences`
- `FMF_SmartOffset`
- `FMF_SolverDiagnostics`
- `FMF_UpdateModel`
- `FMF_MoreSketchCreate_ddb`
- `Sketcher_ArcOverlay`
- `Sketcher_BSplineConvertToNURBS`
- `Sketcher_BSplineDecreaseDegree`
- `Sketcher_BSplineIncreaseDegree`
- `Sketcher_BSplineInsertKnot`
- `Sketcher_CancelSketch`
- `Sketcher_CarbonCopy`
- `Sketcher_CompBSplineShowHideGeometryInformation`
- `Sketcher_CompConstrainTools`
- `Sketcher_CompCreateBSpline`
- `Sketcher_CompCreateConic`
- `Sketcher_CompCreateFillets`
- `Sketcher_CompCreateRectangles`
- `Sketcher_CompCurveEdition`
- `Sketcher_CompDimensionTools`
- `Sketcher_CompExternal`
- `Sketcher_CompLine`
- `Sketcher_CompModifyKnotMultiplicity`
- `Sketcher_CompSlot`
- `Sketcher_CompToggleConstraints`
- `Sketcher_ConstrainBlock`
- `Sketcher_ConstrainCoincidentUnified`
- `Sketcher_ConstrainEqual`
- `Sketcher_ConstrainHorVer`
- `Sketcher_ConstrainParallel`
- `Sketcher_ConstrainPerpendicular`
- `Sketcher_ConstrainSymmetric`
- `Sketcher_ConstrainTangent`
- `Sketcher_CopyClipboard`
- `Sketcher_CreateArc`
- `Sketcher_CreateBSpline`
- `Sketcher_CreateLine`
- `Sketcher_CreatePoint`
- `Sketcher_CreatePolyline`
- `Sketcher_CreateRectangle`
- `Sketcher_CreateRectangle_Center`
- `Sketcher_CreateSlot`
- `Sketcher_CreateText`
- `Sketcher_Cut`
- `Sketcher_DeleteAllConstraints`
- `Sketcher_DeleteAllGeometry`
- `Sketcher_Dimension`
- `Sketcher_Extend`
- `Sketcher_Intersection`
- `Sketcher_JoinCurves`
- `Sketcher_LeaveSketch`
- `Sketcher_Offset`
- `Sketcher_Paste`
- `Sketcher_RectangularArray`
- `Sketcher_RemoveAxesAlignment`
- `Sketcher_RestoreInternalAlignmentGeometry`
- `Sketcher_Rotate`
- `Sketcher_Scale`
- `Sketcher_SelectConflictingConstraints`
- `Sketcher_SelectConstraints`
- `Sketcher_SelectElementsAssociatedWithConstraints`
- `Sketcher_SelectElementsWithDoFs`
- `Sketcher_SelectHorizontalAxis`
- `Sketcher_SelectOrigin`
- `Sketcher_SelectRedundantConstraints`
- `Sketcher_SelectVerticalAxis`
- `Sketcher_SwitchVirtualSpace`
- `Sketcher_Symmetry`
- `Sketcher_ToggleActiveConstraint`
- `Sketcher_ToggleConstruction`
- `Sketcher_ToggleDrivingConstraint`
- `Sketcher_Translate`
- `Sketcher_Trimming`
- `Std_BoxElementSelection`
- `Std_BoxSelection`
- `Std_Properties`
- `Std_UnitsCalculator`
- `Std_WhatsThis`

## SurfaceWorkbench

- FMF commands: 23
- Source command literals: 7
- Not in FMF layout: 1

- Live actions after activation: 466
- Searchable/native-menu dispositions: 0
- Intentional source-only omissions: 1
- Activation time: 21.633 ms

### Verified dispositions

- **Intentional omission:** `Surface_Cut` — no QAction appeared after activating this workbench; the host source comments this command out.

### FMF inventory

- `FMF_Export`
- `FMF_Export3MF`
- `FMF_ExportDXF`
- `FMF_ExportSTEP`
- `FMF_ExportSTL`
- `FMF_Reapply`
- `FMF_RepairReferences`
- `FMF_Restore`
- `FMF_UpdateModel`
- `FMF_Verify`
- `Part_CheckGeometry`
- `Std_BoxElementSelection`
- `Std_BoxSelection`
- `Std_Measure`
- `Std_Properties`
- `Std_UnitsCalculator`
- `Std_WhatsThis`
- `Surface_BlendCurve`
- `Surface_CurveOnMesh`
- `Surface_ExtendFace`
- `Surface_Filling`
- `Surface_GeomFillSurface`
- `Surface_Sections`
