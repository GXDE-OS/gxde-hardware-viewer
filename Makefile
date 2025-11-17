build:
	pylupdate6 gxde-hardware-viewer.py -ts translations/gxde-hardware-viewer_en_US.ts
	pylupdate6 gxde-hardware-viewer.py -ts translations/gxde-hardware-viewer_zh_CN.ts
	bash translate_generation.sh

install:
	mkdir -pv $(DESTDIR)/usr/share/applications
	mkdir -pv $(DESTDIR)/usr/share/gxde-hardware-viewer/translations
	mkdir -pv $(DESTDIR)/usr/bin
	mkdir -pv $(DESTDIR)/usr/share/polkit-1/actions/
	cp -rv gxde-hardware-viewer.desktop $(DESTDIR)/usr/share/applications
	cp -rv gxde-hardware-viewer.py $(DESTDIR)/usr/bin/gxde-hardware-viewer
	cp -rv gxde-hardware-viewer-helper.sh $(DESTDIR)/usr/bin/gxde-hardware-viewer-helper
	cp -rv translations/*.qm $(DESTDIR)/usr/share/gxde-hardware-viewer/translations