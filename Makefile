build:
	pylupdate6 gxde-hardware-viewer.py hardware_info/board_info.py hardware_info/cdrom_info.py hardware_info/cpu_info.py -ts translations/gxde-hardware-viewer_en_US.ts
	pylupdate6 gxde-hardware-viewer.py hardware_info/board_info.py hardware_info/cdrom_info.py hardware_info/cpu_info.py -ts translations/gxde-hardware-viewer_zh_CN.ts
	bash translate_generation.sh

install:
	mkdir -pv $(DESTDIR)/usr/share/applications
	mkdir -pv $(DESTDIR)/usr/share/gxde-hardware-viewer/translations
	mkdir -pv $(DESTDIR)/usr/share/gxde-hardware-viewer/hardware_info
	mkdir -pv $(DESTDIR)/usr/bin
	mkdir -pv $(DESTDIR)/usr/share/polkit-1/actions/
	mkdir -pv $(DESTDIR)/usr/share/gxde-hardware-viewer/icons
	cp -rv polkit/* $(DESTDIR)/usr/share/polkit-1/actions/
	cp -rv gxde-hardware-viewer.desktop $(DESTDIR)/usr/share/applications
	cp -rv gxde-hardware-viewer.py $(DESTDIR)/usr/bin/gxde-hardware-viewer
	cp -rv gxde-hardware-viewer-helper.sh $(DESTDIR)/usr/bin/gxde-hardware-viewer-helper
	cp -rv translations/*.qm $(DESTDIR)/usr/share/gxde-hardware-viewer/translations
	cp -rv icons/*.svg $(DESTDIR)/usr/share/gxde-hardware-viewer/icons
	cp -rv hardware_info/*.py $(DESTDIR)/usr/share/gxde-hardware-viewer/hardware_info/
	cp -rv gxde-logo_new.png $(DESTDIR)/usr/share/gxde-hardware-viewer